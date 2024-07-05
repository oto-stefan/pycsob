import datetime
import logging
import re
import requests
from base64 import b64encode, b64decode
from collections import OrderedDict
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from typing import Any, List

from . import conf

from urllib.parse import urljoin, quote_plus

LOGGER = logging.getLogger('pycsob')


class CsobVerifyError(Exception):
    pass


class PycsobSession(requests.Session):
    """Request session with logging requests."""

    def post(self, url, data=None, json=None, **kwargs):
        LOGGER.info("Pycsob request POST: {}; Data: {}; Json: {}; {}".format(url, data, json, kwargs))
        return super().post(url, data, json, **kwargs)

    def get(self, url, **kwargs):
        LOGGER.info("Pycsob request GET: {}; {}".format(url, kwargs))
        return super().get(url, **kwargs)

    def put(self, url, data=None, **kwargs):
        LOGGER.info("Pycsob request PUT: {}; Data: {}; {}".format(url, data, kwargs))
        return super().put(url, data, **kwargs)

    def send(self, request, **kwargs):
        LOGGER.debug("Pycsob request headers: {}".format(request.headers))
        return super().send(request, **kwargs)


def pkcs1(keyfile: str):
    """Initialize signer/verifier with RSA key."""
    with open(keyfile, "rb") as f:
        key = RSA.importKey(f.read())
    return PKCS1_v1_5.new(key)


def sign(payload, signer):
    """Sign payload."""
    msg = mk_msg_for_sign(payload)
    h = SHA256.new(msg)
    return b64encode(signer.sign(h)).decode()


def verify(payload, signature, verifier):
    """Verify payload signature."""
    msg = mk_msg_for_sign(payload)
    h = SHA256.new(msg)
    return verifier.verify(h, b64decode(signature))


def mk_msg_item(value: Any) -> List[str]:
    """Prepare message item for making signature."""
    data: List[str] = []
    if value in conf.EMPTY_VALUES:
        return data
    if isinstance(value, (list, tuple)):
        for item in value:
            data.extend(mk_msg_item(item))
    elif isinstance(value, (dict, OrderedDict)):
        for item in value.values():
            data.extend(mk_msg_item(item))
    else:
        data.append(str_or_jsbool(value))
    return data


def mk_msg_for_sign(payload: OrderedDict[str, Any]) -> bytes:
    """Prepare message for signature."""
    return '|'.join(mk_msg_item(payload)).encode('utf-8', 'xmlcharrefreplace')


def mk_payload(signer, pairs):
    payload = OrderedDict([(k, v) for k, v in pairs if v not in conf.EMPTY_VALUES])
    payload['signature'] = sign(payload, signer)
    return payload


def mk_url(base_url, endpoint_url, payload=None):
    url = urljoin(base_url, endpoint_url)
    if payload is None:
        return url
    return urljoin(url, '/'.join(map(quote_plus, payload.values())))


def str_or_jsbool(value):
    if isinstance(value, bool):
        return str(value).lower()
    return str(value).strip()


def dttm(format_='%Y%m%d%H%M%S'):
    return datetime.datetime.now().strftime(format_)


def dttm_decode(value):
    """Decode dttm value '20190404091926' to the datetime object."""
    return datetime.datetime.strptime(value, "%Y%m%d%H%M%S")


def validate_response(response, verifier):
    LOGGER.info("Pycsob response: [{}] {}".format(response.status_code, response.text))
    LOGGER.debug("Pycsob response headers: {}".format(response.headers))

    response.raise_for_status()

    data = response.json()
    signature = data.pop('signature')
    payload = OrderedDict()

    for k in conf.RESPONSE_KEYS:
        if k in data:
            payload[k] = data[k]

    if not verify(payload, signature, verifier):
        raise CsobVerifyError('Cannot verify response')

    if "dttm" in payload:
        payload["dttime"] = dttm_decode(payload["dttm"])

    response.extensions = []
    response.payload = payload

    # extensions
    if 'extensions' in data:
        maskclnrp_keys = 'extension', 'dttm', 'maskedCln', 'expiration', 'longMaskedCln'
        for one in data['extensions']:
            if one['extension'] == 'maskClnRP':
                o = OrderedDict()
                for k in maskclnrp_keys:
                    if k in one:
                        o[k] = one[k]
                if verify(o, one['signature'], verifier):
                    response.extensions.append(o)
                else:
                    raise CsobVerifyError('Cannot verify masked card extension response')

    return response


PROVIDERS = (
    (conf.CARD_PROVIDER_VISA, re.compile(r'^4\d{5}$')),
    (conf.CARD_PROVIDER_AMEX, re.compile(r'^3[47]\d{4}$')),
    (conf.CARD_PROVIDER_DINERS, re.compile(r'^3(?:0[0-5]|[68][0-9])[0-9]{4}$')),
    (conf.CARD_PROVIDER_JCB, re.compile(r'^(?:2131|1800|35[0-9]{2})[0-9]{2}$')),
    (conf.CARD_PROVIDER_MC, re.compile(r'^5[1-5][0-9]{4}|222[1-9][0-9]{2}|22[3-9][0-9]{4}|2[3-6][0-9]{5}|27[01][0-9]{4}|2720[0-9]{2}$')),
)


def get_card_provider(long_masked_number):
    for provider_id, rx in PROVIDERS:
        if rx.match(long_masked_number[:6]):
            return provider_id, conf.CARD_PROVIDERS[provider_id]
    return None, None


def encode_merchant_data(merchant_data):
    """Encode merchant data. Raise ValueError if data length > 255."""
    if merchant_data is not None:
        merchant_data = b64encode(merchant_data).decode("UTF-8")
        if len(merchant_data) > 255:
            raise ValueError('Merchant data length encoded to BASE64 is over 255 chars')
    return merchant_data
