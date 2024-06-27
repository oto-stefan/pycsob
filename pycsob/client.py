# coding: utf-8
from base64 import b64decode
import json
import requests.adapters
from collections import OrderedDict
from dataclasses import dataclass, fields
from enum import Enum, unique
from typing import Any, Dict, List, Optional, Union

from . import conf, utils


class HTTPAdapter(requests.adapters.HTTPAdapter):
    """
    HTTP adapter with default timeout
    """

    def send(self, request, **kwargs):
        kwargs.setdefault('timeout', conf.HTTP_TIMEOUT)
        return super(HTTPAdapter, self).send(request, **kwargs)


class ConvertMixin:
    """Convert instance into ordered dict."""

    def to_dict(self) -> Dict[str, Union[str, Dict]]:
        data = []
        for field in fields(self):
            value = getattr(self, field.name)
            if value in conf.EMPTY_VALUES:
                continue
            if hasattr(value, 'to_dict'):
                value = value.to_dict()
            data.append((field.name, getattr(self, f"_format_{field.name}", lambda v: v)(value)))
        return OrderedDict(data)


@dataclass
class CartItem(ConvertMixin):
    """Cart item for creating card payment."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Basic-methods#item---cart-item-object-cart-

    name: str
    quantity: int
    amount: int
    description: Optional[str] = None
    
    def _format_name(self, value: str) -> str:
        return value[:20].rstrip()
    
    def _format_description(self, value: str) -> str:
        return value[:40].rstrip()


@dataclass
class CustomerAccount(ConvertMixin):
    """Customer account data."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#customeraccount-data-

    createdAt: Optional[str] = None
    changedAt: Optional[str] = None
    changedPwdAt: Optional[str] = None
    orderHistory: Optional[int] = None
    paymentsDay: Optional[int] = None
    paymentsYear: Optional[int] = None
    oneclickAdds: Optional[int] = None
    suspicious: Optional[bool] = None


@unique
class CustomerLoginType(Enum):
    """Type of customer login."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#customerlogin-data-

    GUEST = "guest"
    ACCOUNT = "account"
    FEDERATED = "federated"
    ISSUER = "issuer"
    THIRDPARTY = "thirdparty"
    FIDO = "fido"
    FIDO_SIGNED = "fido_signed"
    API = "api"


@dataclass
class CustomerLogin(ConvertMixin):
    """Customer login data."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#customerlogin-data-

    auth: Optional[CustomerLoginType] = None
    authAt: Optional[str] = None
    authData: Optional[str] = None

    def _format_auth(self, value: CustomerLoginType) -> str:
        return value.value


@dataclass
class CustomerData(ConvertMixin):
    """Customer data for creating card payment."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#customer-data-

    name: str
    email: Optional[str] = None
    homePhone: Optional[str] = None
    workPhone: Optional[str] = None
    mobilePhone: Optional[str] = None
    account: Optional[CustomerAccount] = None
    login: Optional[CustomerLogin] = None
    
    def _format_name(self, value: str) -> str:
        return value[:45].rstrip()
    
    def _format_description(self, value: str) -> str:
        return value[:100].rstrip()


@dataclass
class OrderAddress(ConvertMixin):
    """Order address (billing or shipping)."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#orderaddress-data-

    address1: str
    address2: Optional[str] = None
    address3: Optional[str] = None
    city: str = ""
    zip: str = ""
    country: str = ""
    state: Optional[str] = None
    
    def _format_address1(self, value: str) -> str:
        return value[:50].rstrip()
    
    def _format_address2(self, value: str) -> str:
        return value[:50].rstrip()
    
    def _format_address3(self, value: str) -> str:
        return value[:50].rstrip()
    
    def _format_city(self, value: str) -> str:
        return value[:50].rstrip()
    
    def _format_zip(self, value: str) -> str:
        return value[:16].rstrip()


@dataclass
class OrderGiftcards(ConvertMixin):
    """Order giftcards data."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#ordergiftcards-data-

    totalAmount: Optional[int] = None
    currency: Optional[str] = None
    quantity: Optional[int] = None


@unique
class OrderType(Enum):
    """Type of order."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#order-data-

    PURCHASE = "purchase"
    BALANCE = "balance"
    PREPAID = "prepaid"
    CASH = "cash"
    CHECK = "check"


@unique
class OrderDeliveryMode(Enum):
    """Delivery mode of order."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#order-data-

    ELECTRONIC = 0
    SAME_DAY = 1
    NEXT_DAY = 2
    LATER = 3


@dataclass
class Order(ConvertMixin):
    """Order data for creating card payment."""
    # Documentation: https://github.com/csob/paymentgateway/wiki/Purchase-metadata#order-data-

    type: Optional[OrderType] = None
    availability: Optional[str] = None
    delivery: Optional[str] = None
    deliveryMode: Optional[OrderDeliveryMode] = None
    deliveryEmail: Optional[str] = None
    nameMatch: Optional[bool] = None
    addressMatch: Optional[bool] = None
    billing: Optional[OrderAddress] = None
    shipping: Optional[OrderAddress] = None
    shippingAddedAt: Optional[str] = None
    reorder: Optional[bool] = None
    giftcards: Optional[OrderGiftcards] = None

    def _format_type(self, value: OrderType) -> str:
        return value.value

    def _format_deliveryMode(self, value: OrderDeliveryMode) -> str:
        return str(value.value)

    def _format_deliveryEmail(self, value: str) -> str:
        return value[:100].rstrip()


class CsobClient(object):

    def __init__(self, merchant_id, base_url, private_key_file, csob_pub_key_file):
        """
        Initialize Client

        :param merchant_id: Your Merchant ID (you can find it in POSMerchant)
        :param base_url: Base API url development / production
        :param private_key_file: Path to generated private key file
        :param csob_pub_key_file: Path to CSOB public key
        """
        self.merchant_id = merchant_id
        self.base_url = base_url
        self.f_key = private_key_file
        self.f_pubkey = csob_pub_key_file

        session = utils.PycsobSession()
        session.headers = conf.HEADERS
        session.mount('https://', HTTPAdapter())
        session.mount('http://', HTTPAdapter())

        self._client = session

    def payment_init(
        self,
        order_no: Union[int, str],
        total_amount: Union[int, str],
        return_url: str,
        description: str,
        cart: Optional[List[CartItem]] = None,
        customer_id: Optional[str] = None,
        currency: str = 'CZK',
        language: str = 'cs',
        close_payment: bool = True,
        return_method: str = 'POST',
        pay_operation: str = 'payment',
        ttl_sec: int = 600,
        logo_version: Optional[int] = None,
        color_scheme_version: Optional[int] = None,
        merchant_data: Optional[bytearray] = None,
        customer_data: Optional[CustomerData] = None,
        order: Optional[Order] = None,
        custom_expiry: Optional[str] = None,
        pay_method: str = 'card',
    ) -> OrderedDict[str, Any]:
        """
        Initialize transaction, sum of cart items must be equal to total amount
        If cart is None, we create it for you from total_amount and description values.

        Cart example::

            cart = [
                CartItem(name='Order in sho XYZ', quantity=5, amount=12345),
                CartItem(name='Postage', quantity=1, amount=0),
            ]

        :param order_no: order number
        :param total_amount:
        :param return_url: URL to be returned to from payment gateway
        :param cart: items in cart, currently min one item, max two as mentioned in CSOB spec
        :param description: product name - it is a part of the cart
        :param customer_id: optional customer id
        :param language: supported languages: 'cs', 'en', 'de', 'sk', 'hu', 'it', 'jp', 'pl', 'pt', 'ro', 'ru', 'sk',
                                              'es', 'tr' or 'vn'
        :param currency: supported currencies: 'CZK', 'EUR', 'USD', 'GBP'
        :param close_payment:
        :param return_method: method which be used for return to shop from gateway POST (default) or GET
        :param pay_operation: `payment`, `customPayment` or `oneclickPayment`
        :param ttl_sec: number of seconds to the timeout
        :param logo_version: Logo version number
        :param color_scheme_version: Color scheme version number
        :param merchant_data: bytearray of merchant data
        :param customer_data: Additional customer purchase data
        :param order: Additional purchase data related to the order
        :param custom_expiry: Custom payment expiration, format YYYYMMDDHHMMSS
        :param pay_method: 'card' = card payment, 'card#LVP' = card payment with low value payment
        :return: response from gateway as OrderedDict
        """

        # fill cart if not set
        if not cart:
            cart = [CartItem(name=description, quantity=1, amount=total_amount)]

        payload = utils.mk_payload(self.f_key, pairs=(
            ('merchantId', self.merchant_id),
            ('orderNo', str(order_no)),
            ('dttm', utils.dttm()),
            ('payOperation', pay_operation),
            ('payMethod', pay_method),
            ('totalAmount', total_amount),
            ('currency', currency),
            ('closePayment', close_payment),
            ('returnUrl', return_url),
            ('returnMethod', return_method),
            ('cart', [item.to_dict() for item in cart]),
            ('customer', customer_data.to_dict() if customer_data is not None else None),
            ('order', order.to_dict() if order is not None else None),
            ('merchantData', utils.encode_merchant_data(merchant_data)),
            ('customerId', customer_id),
            ('language', language[:2]),
            ('ttlSec', ttl_sec),
            ('logoVersion', logo_version),
            ('colorSchemeVersion', color_scheme_version),
            ('customExpiry', custom_expiry),
        ))
        url = utils.mk_url(base_url=self.base_url, endpoint_url='payment/init')
        r = self._client.post(url, data=json.dumps(payload))
        return utils.validate_response(r, self.f_pubkey)

    def get_payment_process_url(self, pay_id):
        """
        :param pay_id: pay_id obtained from payment_init()
        :return: url to process payment
        """
        return utils.mk_url(
            base_url=self.base_url,
            endpoint_url='payment/process/',
            payload=self.req_payload(pay_id=pay_id)
        )

    def gateway_return(self, datadict):
        """
        Return from gateway as OrderedDict

        :param datadict: data from request in dict
        :return: verified data or raise error
        """
        o = OrderedDict()
        for k in conf.RESPONSE_KEYS:
            if k in datadict:
                o[k] = int(datadict[k]) if k in ('resultCode', 'paymentStatus') else datadict[k]
        if not utils.verify(o, datadict['signature'], self.f_pubkey):
            raise utils.CsobVerifyError('Unverified gateway return data')
        if "dttm" in o:
            o["dttime"] = utils.dttm_decode(o["dttm"])
        if 'merchantData' in o:
            o['merchantData'] = b64decode(o['merchantData'])
        return o

    def payment_status(self, pay_id):
        url = utils.mk_url(
            base_url=self.base_url,
            endpoint_url='payment/status/',
            payload=self.req_payload(pay_id=pay_id)
        )
        r = self._client.get(url=url)
        return utils.validate_response(r, self.f_pubkey)

    def payment_reverse(self, pay_id):
        url = utils.mk_url(
            base_url=self.base_url,
            endpoint_url='payment/reverse/'
        )
        payload = self.req_payload(pay_id)
        r = self._client.put(url, data=json.dumps(payload))
        return utils.validate_response(r, self.f_pubkey)

    def payment_close(self, pay_id, total_amount=None):
        url = utils.mk_url(
            base_url=self.base_url,
            endpoint_url='payment/close/'
        )
        payload = self.req_payload(pay_id, totalAmount=total_amount)
        r = self._client.put(url, data=json.dumps(payload))
        return utils.validate_response(r, self.f_pubkey)

    def payment_refund(self, pay_id, amount=None):
        url = utils.mk_url(
            base_url=self.base_url,
            endpoint_url='payment/refund/'
        )

        payload = self.req_payload(pay_id, amount=amount)
        r = self._client.put(url, data=json.dumps(payload))
        return utils.validate_response(r, self.f_pubkey)

    def customer_info(self, customer_id):
        """
        :param customer_id: e-shop customer ID
        :return: data from JSON response or raise error
        """
        url = utils.mk_url(
            base_url=self.base_url,
            endpoint_url='echo/customer'
        )
        payload = utils.mk_payload(self.f_key, pairs=(
            ('merchantId', self.merchant_id),
            ('customerId', customer_id),
            ('dttm', utils.dttm())
        ))
        r = self._client.post(url, data=json.dumps(payload))
        return utils.validate_response(r, self.f_pubkey)

    def echo(self, method='POST'):
        """
        Echo call for development purposes/gateway tests

        :param method: request method (GET/POST), default is POST
        :return: data from JSON response or raise error
        """
        payload = utils.mk_payload(self.f_key, pairs=(
            ('merchantId', self.merchant_id),
            ('dttm', utils.dttm())
        ))
        if method.lower() == 'post':
            url = utils.mk_url(
                base_url=self.base_url,
                endpoint_url='echo/'
            )
            r = self._client.post(url, data=json.dumps(payload))
        else:
            url = utils.mk_url(
                base_url=self.base_url,
                endpoint_url='echo/',
                payload=payload
            )
            r = self._client.get(url)

        return utils.validate_response(r, self.f_pubkey)

    def req_payload(self, pay_id, **kwargs):
        pairs = (
            ('merchantId', self.merchant_id),
            ('payId', pay_id),
            ('dttm', utils.dttm()),
        )
        for k, v in kwargs.items():
            if v not in conf.EMPTY_VALUES:
                pairs += ((k, v),)
        return utils.mk_payload(keyfile=self.f_key, pairs=pairs)

    def button_init(
            self, order_no, total_amount, client_ip, return_url,
            language='cs', return_method='POST', merchant_data=None):
        "Get url to the button."

        payload = utils.mk_payload(self.f_key, pairs=(
            ('merchantId', self.merchant_id),
            ('orderNo', str(order_no)),
            ('dttm', utils.dttm()),
            ('clientIp', client_ip),
            ('totalAmount', total_amount),
            ('currency', 'CZK'),
            ('returnUrl', return_url),
            ('returnMethod', return_method),
            ('brand', 'csob'),
            ('merchantData', utils.encode_merchant_data(merchant_data)),
            ('language', language[:2]),
        ))
        url = utils.mk_url(base_url=self.base_url, endpoint_url='button/init')
        r = self._client.post(url, data=json.dumps(payload))
        return utils.validate_response(r, self.f_pubkey)
