"""
Helper implementations for L{txwebutils.csauth}.
"""
from zope.interface import implementer

from ..encutils import get_unicode_params
from .icsauth import ILoginResource
from .cred import UnicodeUsernamePassword


@implementer(ILoginResource)
class BasicLoginResource(object):
    """
    This is a basic default implementation of
    L{txwebutils.csauth.itxcsauth.ILoginResource}.
    """
    def render_loginpage(self, request):
        params = get_unicode_params(request)
        ctoken = params.get("ctoken", [""])[0]
        return u"""<HTML>
    <HEAD>
        <TITLE>Login</TITLE>
    </HEAD>
    <BODY>
        <H1>Login</H1>
        <HR><BR>
        <FORM action="?action=login&ctoken={ctoken}" method="post">
            <LABEL for="username">Username:</LABEL><br>
            <INPUT type="text" id="username", name="username"><br>
            <LABEL for="password">Passowrd:</LABEL><br>
            <INPUT type="password" id="password", name="password"><br>
            <input type="submit" value="Login">
        </FORM>
    </BODY>
</HTML>
""".format(ctoken=ctoken)

    def handle_login_response(self, params):
        username = params.get("username", [""])[0]
        password = params.get("password", [""])[0]
        return UnicodeUsernamePassword(username, password)
    
    def render_login_failed(self, request):
        params = get_unicode_params(request)
        ctoken = params.get("ctoken", [""])[0]
        request.setResponseCode(401)
        return u"""<HTML>
    <HEAD>
        <TITLE>Login failed</TITLE>
    </HEAD>
    <BODY>
        <H1>Login failed</H1>
        <HR><BR>
        <P>Login failed</p><br>
        <A href="?action=login&ctoken={ctoken}">Click here to return to login</A>
    </BODY>
</HTML>""".format(ctoken=ctoken)

    def render_invalid_login(self, request):
        request.setResponseCode(400)
        return u"""<HTML>
    <HEAD>
        <TITLE>Error</TITLE>
    </HEAD>
    <BODY>
        <H1>Error</H1>
        <HR><BR>
        <P>Login request invalid.</P>
    </BODY>
</HTML>
"""
