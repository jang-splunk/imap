# File: request_handler.py
#
# Copyright (c) 2016-2023 Splunk Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions
# and limitations under the License.

import base64
import json
import os

import requests
from django.http import HttpResponse

from imap_consts import *


def handle_request(request, path_parts):
    return IMAPRequestHandler(request, path_parts).handle_request()


def _get_dir_name_from_app_name(app_name):
    app_name = ''.join([x for x in app_name if x.isalnum()])
    app_name = app_name.lower()
    if not app_name:
        app_name = "app_for_phantom"
    return app_name


class IMAPRequestHandler:
    def __init__(self, request, path_parts):
        self._request = request
        self._path_parts = path_parts
        self._rsh = None

    def _return_error(self, error_msg, status):
        state = self._rsh.load_state()
        state['error'] = True
        self._rsh.save_state(state)
        return HttpResponse(error_msg, status=status, content_type="text/plain")

    def _get_oauth_token(self, code):
        state = self._rsh.load_state()

        client_id = state['client_id']
        redirect_uri = state['redirect_url']
        client_secret = base64.b64decode(state['client_secret']).decode()
        proxy = state['proxy']
        token_url = state['token_url']

        body = {
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'client_id': client_id,
            'code': code,
            'client_secret': client_secret
        }

        try:
            r = requests.post(token_url, data=body, proxies=proxy, timeout=DEFAULT_REQUEST_TIMEOUT)
            r.raise_for_status()
            resp_json = r.json()
        except Exception as e:
            return False, self._return_error(
                "Error retrieving OAuth Token: {}".format(str(e)),
                401
            )
        state['oauth_token'] = resp_json
        self._rsh.save_state(state)

        return True, None

    def handle_request(self):
        try:
            GET = self._request.GET

            asset_id = GET.get('state')
            self._rsh = RequestStateHandler(asset_id)
            error = GET.get('error')
            if error:
                error_msg = GET.get('error_description')
                return self._return_error(error_msg, 401)

            code = GET.get('code')

            ret_val, http_object = self._get_oauth_token(code)

            if ret_val is False:
                return http_object

            return HttpResponse("You can now close this page", content_type="text/plain")
        except Exception as e:
            return self._return_error("Error handling request: {}".format(str(e)), 400)


class RequestStateHandler:
    def __init__(self, asset_id):
        asset_id = str(asset_id)
        if asset_id and asset_id.isalnum():
            self._asset_id = asset_id
        else:
            raise AttributeError("RequestStateHandler got invalid asset_id")

    def _get_state_file(self):
        dirpath = os.path.split(__file__)[0]
        state_file = "{0}/{1}_state.json".format(dirpath, self._asset_id)
        return state_file

    def delete_state(self):
        state_file = self._get_state_file()
        try:
            os.remove(state_file)
        except Exception:
            pass

        return True

    def save_state(self, state):
        state_file = self._get_state_file()
        try:
            with open(state_file, 'w+') as fp:
                fp.write(json.dumps(state))
        except Exception:
            pass

        return True

    def load_state(self):
        state_file = self._get_state_file()
        state = {}
        try:
            with open(state_file, 'r') as fp:
                in_json = fp.read()
                state = json.loads(in_json)
        except Exception:
            pass

        return state
