"""
txwebutils.csauth - cross site auth framework for twisted web.
"""
import random
import string
import json

from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web.util import redirectTo
from twisted.cred.credentials import Anonymous
from twisted.cred.error import Unauthorized, LoginFailed

import treq

from expiringdict import ExpiringDict

from ..encutils import unicode_response, get_unicode_params
from .icsauth import IWebAuthPermission, ILoginCookie, IUserData
from .cred import UnicodeUsernamePassword
from . import cookies  # registers the adapters

"""
CS AUTH FLOW
=================
1. Web Client ("CLIENT") opens login page on webserver ("WEB")
2.WEB sends a POST to the authserver/authentication_url ("AUTH"/"AUTH_URL")
    with params ?action=prepare&token=TOKEN$secret=SECRET
3. AUTH checks if TOKEN/SECRET combination is valid:
    -> (3.1) if invalid, AUTH responds to request with error message
    -> (3.2) if valid, AUTH creates a CLIENT_TOKEN, registers it with a timeout,
        then sends it as the response to WEB
4. WEB redirects CLIENT to GET AUTH/AUTH_URL?action=check&ctoken=CLIENT_TOKEN
5. WEB GETs above URL
6. AUTH checks if login cookie is present:
    -> (6.1) if it is, redirect CLIENT to WEB/loginpage?action=callback&ctoken=CLIENT_TOKEN
    -> (6.2) otherwise, redirect CLIENT to AUTH/AUTH_URL?action=login&ctoken=CLIENT_TOKEN
        6.2.1 CLIENT GETs above URL
        6.2.2 AUTH responds with login page
        6.2.3 CLIENT sends login data
        6.2.4 AUTH checks credentials
            -> if valid, continue with 6.1
            -> if invalid continue with 6.2
7. CLIENT GETs URL mentioned in 6.1
8. WEB GETs AUTH/AUTH_URL?action=validate&token=TOKEN&secret=SECRET%ctoken=CLIENT_TOKEN
9. AUTH checks if ctoken is valid login and token and secret are valid
    -> if token and secret invalid, respond error message
    -> if ctoken is invalid login, respond with error message
    -> if ctoken is valid, respond with user data
10. if above was successfull, WEB grants access to CLIENT
"""

_URL_ENCODING = "utf-8"


class WebLoginResource(Resource):
    """
    This L{twisted.web.resource.Resource} is the webserver's entrypoint
    for cross site authentication. It should be served when the client
    is opening the loginpage.
    
    @param auth_url: the URL to the auth webserver, more specifically to
        an L{txwebutils.csauth.AuthResource}. This should follow the
        C{'https://'} scheme to prevent leak of sensitive data.
    @type auth_url: L{six.text_type}
    @param token: token used to identify this webserver to the authserver
    @type token: L{six.text_type}
    @param secret: the secret matching the token
    @type secret: L{str}
    """
    isLeaf = True
    
    def __init__(self, auth_url, token=None, secret=None):
        Resource.__init__(self)
        self._auth_url = auth_url
        self._token = token
        self._secret = secret
    
    def on_login(self, request, userdata):
        """
        This method will be called when a user successfully logged in.
        The result of this call will be served as the response to the client.
        
        Deferred and unicode return values are allowed.
        
        @param request: the request of the user.
        @type request: L{twisted.web.server.Request}
        @param userdata: the userdata returned from the auth server
        @type userdata: ?
        """
        raise NotImplementedError("This method should be overridden in a subclass!")
    
    @unicode_response
    @defer.inlineCallbacks
    def render_GET(self, request):
        params = get_unicode_params(request)
        action = params.get(u"action", [u"login"])[0]
        
        if action == u"login":
            # client wants to login
            # first of, prepare request
            r = yield treq.post(
                self._auth_url,
                params={
                    u"action": u"prepare",
                    u"token": self._token,
                    u"secret": self._secret,
                }
            )
            response = yield r.json()
            status = response.get(u"status", u"error")
            if status == u"error":
                # preparation failed
                reason = response.get("reason", "Unknown")
                request.setResponseCode(500)
                defer.returnValue(u"Error: {}".format(reason))
            elif status == u"success":
                # preparations succeeded
                ctoken = response.get("client_token", None)
                if ctoken is None:
                    # no ctoken aquired, this is an error
                    request.setResponseCode(500)
                    defer.returnValue(u"Error: authentication server did not send a client token.")
                # continued below
            else:
                # invalid response
                request.setResponseCode(500)
                defer.returnValue(u"Error: authentication server send invalid response.")
            
            # we now have a client token, time to redirect the client
            # to the auth server
            defer.returnValue(
                redirectTo("{}?action=check&ctoken={}".format(
                    self._auth_url,
                    ctoken,
                    ).encode(_URL_ENCODING),
                request,
                )
            )
                         
        elif action == u"callback":
            # client is back from auth server
            ctoken = params.get(u"ctoken", [None])[0]
            r = yield treq.get(
                self._auth_url,
                params={
                    u"action": u"validate",
                    u"token": self._token,
                    u"secret": self._secret,
                    u"ctoken": ctoken,
                }
            )
            response = yield r.json()
            if response.get(u"status", u"error") == u"success":
                userdata = response.get(u"userdata", None)
                result = yield self.on_login(request, userdata)
                defer.returnValue(result)
            else:
                # login invalid, attempt another login
                defer.returnValue(
                    redirectTo(
                        b"?action=login",
                        request,
                    )
                )
        else:
            request.setResponseCode(404)
            defer.returnValue(u"Error: Invalid action specified.")


class AuthResource(Resource):
    """
    This L{twisted.web.resource.Resource} is the authservers's interface.
    
    @cvar MAX_TOKEN_NUM: maximal number of tokens to store at once.
    @type MAX_TOKEN_NUM: L{int}
    @cvar MAX_TOKEN_TTL: maximal lifetime of a token in secods
    @type MAX_TOKEN_TTL: L{int}
    
    @param token_portal: the portal used to check if another website is
        allowed to actually use this site for cross-site-auth
    @type token_portal: L{twisted.cred.portal.Portal}
    @param user_portal: the portal used to check user logins
    @type user_portal: L{twisted.cred.portal.Portal}
    @param login_resource: the resource used to render login pages and errors
    @type login_resource: L{txwebtuisl.csauth.icsauth.ILoginResource}
    @param url: full URL to this resource. Defaults to empty (=relative to itself).
    @type url: L{six.text_type}
    """
    MAX_TOKEN_NUM = 512
    MAX_TOKEN_TTL = 60 * 15  # 15 min
    
    _TOKEN_CHARACTERS = string.ascii_letters + string.digits
    _TOKEN_LENGTH = 16
    
    _TOKEN_STATE_LOGIN = 0
    _TOKEN_STATE_CB = 1
    
    isLeaf = True
    
    def __init__(self, token_portal, user_portal, login_resource, url=u""):
        self._user_portal = user_portal
        self._token_portal = token_portal
        self._tokens = ExpiringDict(
            max_len=self.MAX_TOKEN_NUM,
            max_age_seconds=self.MAX_TOKEN_TTL,
        )
        self._login_resource = login_resource
        self._url = url
    
    def _new_ctoken(self):
        """
        Generate a new client token.
        
        @return: the client token
        @rtype: L{six.text_type}
        """
        ctoken = None
        while (ctoken is None) or (ctoken in self._tokens):
            # generate a new token
            ctoken = u"".join(
                random.sample(self._TOKEN_CHARACTERS, self._TOKEN_LENGTH),
            )
        return ctoken
    
    @unicode_response
    @defer.inlineCallbacks
    def render_GET(self, request):
        params = get_unicode_params(request)
        action = params.get(u"action", [None])[0]
        
        if action == u"login":
            # client wants to login
            result = yield self._login_resource.render_loginpage(request)
            defer.returnValue(result)
        elif action == u"check":
            # check if client is already logged in
            # first, check for ctoken
            ctoken = params.get(u"ctoken", [None])[0]
            if ctoken not in self._tokens:
                # invalid ctoken
                html = yield self._login_resource.render_invalid_login(request)
                defer.returnValue(html or u"Error: invalid ctoken!")
            
            session = request.getSession()
            cookie = ILoginCookie(session)
            
            if cookie.userdata is not None:
                # client is logged in
                state, perm, _ = self._tokens[ctoken]
                self._tokens[ctoken] = (self._TOKEN_STATE_CB, perm, cookie.userdata)
                defer.returnValue(
                    redirectTo(
                        u"{}?action=callback&ctoken={}".format(
                            perm.callback_url,
                            ctoken,
                        ).encode(_URL_ENCODING),
                        request,
                    )
                )
            else:
                # client is not already logged in, redirect to login
                defer.returnValue(
                    redirectTo(
                        u"{}?action=login&ctoken={}".format(
                            self._url,
                            ctoken,
                            ).encode(
                            _URL_ENCODING,
                            ),
                        request,
                    )
                )
        elif action == u"validate":
            # website wants to validate login information
            ctoken = params.get(u"ctoken", [None])[0]
            if (ctoken is None) or (ctoken not in self._tokens):
                defer.returnValue(u'{"status": "error", "reason": "ctoken invalid!"}')
            else:
                state, perm, userdata = self._tokens[ctoken]
                if (state != self._TOKEN_STATE_CB):
                    defer.returnValue(u'{"status": "error", "reason": "ctoken did not complete login!"}')
                elif perm is None:
                    defer.returnValue(u'{"status": "error", "reason": "site does not have permission for login!"}')
                else:
                    cleaned = yield perm.userdata_to_dict(userdata)
                    defer.returnValue(
                        json.dumps(
                            {
                                u"status": u"success",
                                u"userdata": cleaned,
                            },
                        )
                    )
        else:
            # unknown action
            request.setResponseCode(404)
            defer.returnValue(u"Error: Invalid action specified.")
    
    @unicode_response
    @defer.inlineCallbacks
    def render_POST(self, request):
        params = get_unicode_params(request)
        action = params.get(u"action", [u"login"])[0]
        
        if action == u"prepare":
            # prepare client token
            token = params.get(u"token", [None])[0]
            secret = params.get(u"secret", [None])[0]
            
            if (token is None) and (secret is None):
                # anonymous website
                credentials = Anonymous()
            elif (token is None) or (secret is None):
                # one value is missing, invalid request
                defer.returnValue(u'{"status": "error", "reason": "token OR secret missing"}')
            else:
                # token / secret provided
                credentials = UnicodeUsernamePassword(token, secret)
            
            try:
                _, perm, logout = yield self._token_portal.login(credentials, None, IWebAuthPermission)
            except (Unauthorized, LoginFailed):
                defer.returnValue(u'{"status": "error", "reason": "token/secret invalid"}')
            else:
                # this is not an interactive season, so call logout immediately
                logout()
            
            ctoken = self._new_ctoken()
            self._tokens[ctoken] = (self._TOKEN_STATE_LOGIN, perm, None)
            defer.returnValue(u'{"status": "success", "client_token": "' + ctoken + '"}')
        elif action == u"login":
            # login credentials
            params = get_unicode_params(request)
            ctoken = params.get("ctoken", [None])[0]
            
            if ctoken not in self._tokens:
                # invalid client token
                html = (yield self._login_resource.render_invalid_login(request)) or u"Error: Invalid ctoken"
                defer.returnValue(html)
            
            credentials = self._login_resource.handle_login_response(params)
            
            # attempt login
            try:
                _, userdata, logout = yield self._user_portal.login(credentials, None, IUserData)
            except (Unauthorized, LoginFailed):
                # invalid login
                response = (yield self._login_resource.render_login_failed(request)) or u"Login failed"
                defer.returnValue(response)
            else:
                # login successfull
                # first off, call logout as twisted cred wants
                logout()
                # secondly, set the client login cookie
                session = request.getSession()
                cookie = ILoginCookie(session)
                cookie.userdata = userdata
                # thirdly, prepare the userdata
                _, perm, _2 = self._tokens[ctoken]
                self._tokens[ctoken] = (self._TOKEN_STATE_CB, perm, userdata)
                # finally, redirect to callback
                defer.returnValue(
                    redirectTo(
                        u"{}?action=callback&ctoken={}".format(
                            perm.callback_url,
                            ctoken,
                        ).encode(_URL_ENCODING),
                        request,
                    )
                )
        else:
            # unknown action
            request.setResponseCode(404)
            defer.returnValue(u"Error: Invalid action specified.")
