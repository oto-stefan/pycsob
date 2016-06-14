# coding: utf-8
import os
import json
from collections import OrderedDict
from unittest import TestCase
from urllib3_mock import Responses

from pycsob import conf, utils
from pycsob.client import CsobClient

KEY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fixtures', 'test.key'))
PAY_ID = '34ae55eb69e2cBF'

responses = Responses(package='requests.packages.urllib3')


class CsobClientTests(TestCase):

    def setUp(self):
        self.c = CsobClient(merchant_id='MERCHANT',
                            base_url='https://gw.cz',
                            private_key_file=KEY_PATH,
                            csob_pub_key_file=KEY_PATH)

    @responses.activate
    def test_echo_post(self):
        resp_payload = utils.mk_payload(KEY_PATH, pairs=(
            ('dttm', utils.dttm()),
            ('resultCode', conf.RETURN_CODE_OK),
            ('resultMessage', 'OK'),
        ))
        responses.add(responses.POST, '/echo/', body=json.dumps(resp_payload),
                      status=200, content_type='application/json')
        out = self.c.echo()
        assert out['dttm'] == resp_payload['dttm']
        assert out['resultCode'] == conf.RETURN_CODE_OK

        sig = resp_payload.pop('signature')
        assert utils.verify(out, sig, KEY_PATH)

    @responses.activate
    def test_echo_get(self):
        payload = utils.mk_payload(KEY_PATH, pairs=(
            ('merchantId', self.c.merchant_id),
            ('dttm', utils.dttm()),
        ))
        resp_payload = utils.mk_payload(KEY_PATH, pairs=(
            ('dttm', utils.dttm()),
            ('resultCode', conf.RETURN_CODE_OK),
            ('resultMessage', 'OK'),
        ))
        url = utils.mk_url('/', 'echo/', payload)
        responses.add(responses.GET, url, body=json.dumps(resp_payload),
                      status=200, content_type='application/json')
        out = self.c.echo(method='GET')
        assert out['dttm'] == resp_payload['dttm']
        assert out['resultCode'] == conf.RETURN_CODE_OK

    def test_sign_message(self):
        msg = 'Příliš žluťoučký kůň úpěl ďábelské ódy.'
        payload = utils.mk_payload(KEY_PATH, pairs=(
            ('merchantId', self.c.merchant_id),
            ('dttm', utils.dttm()),
            ('description', msg)
        ))
        assert payload['description'] == msg
        sig = payload.pop('signature')
        assert utils.verify(payload, sig, KEY_PATH)

    @responses.activate
    def test_payment_init_success(self):
        resp_url = '/payment/init'
        resp_payload = utils.mk_payload(KEY_PATH, pairs=(
            ('payId', PAY_ID),
            ('dttm', utils.dttm()),
            ('resultCode', conf.RETURN_CODE_OK),
            ('resultMessage', 'OK'),
            ('paymentStatus', 1)
        ))
        responses.add(responses.POST, resp_url, body=json.dumps(resp_payload), status=200)
        out = self.c.payment_init(order_no=666, total_amount='66600', return_url='http://example.com',
                                  description='Nějaký popis')

        assert out['paymentStatus'] == conf.PAYMENT_STATUS_INIT
        assert out['resultCode'] == conf.RETURN_CODE_OK
        assert len(responses.calls) == 1

    @responses.activate
    def test_payment_init_bad_cart(self):
        cart = [
            OrderedDict([
                ('name', 'Order in sho XYZ'),
                ('quantity', 5),
                ('amount', 12345),
            ]),
            OrderedDict([
                ('name', 'Postage'),
                ('quantity', 1),
                ('amount', 0),
            ])
        ]
        resp_payload = utils.mk_payload(KEY_PATH, pairs=(
            ('payId', PAY_ID),
            ('dttm', utils.dttm()),
            ('resultCode', conf.RETURN_CODE_PARAM_INVALID),
            ('resultMessage', "Invalid 'cart' amounts, does not sum to totalAmount"),
            ('paymentStatus', conf.PAYMENT_STATUS_REJECTED)
        ))
        resp_url = '/payment/init'
        responses.add(responses.POST, resp_url, body=json.dumps(resp_payload), status=200)
        out = self.c.payment_init(order_no=666, total_amount='2200000', return_url='http://',
                                  description='X', cart=cart)

        assert out['paymentStatus'] == conf.PAYMENT_STATUS_REJECTED
        assert out['resultCode'] == conf.RETURN_CODE_PARAM_INVALID

