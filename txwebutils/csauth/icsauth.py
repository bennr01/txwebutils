"""
Interface declarations for L{txwebutils.csauth}
"""
from zope.interface import Interface

from twisted.cred.credentials import ICredentials


class IUnicodeUsernamePassword(ICredentials):
    """
    Unicode version of L{twisted.cred.credentials.IUsernamePassword}.
    
    @ivar username: The username associated with these credentials.
    @type username: L{six.text_type}
    @ivar password: The password associated with these credentials.
    @type password: L{six.text_type}
    """

    def checkPassword(password):
        """
        Validate these credentials against the correct password.
        
        @param password: The correct, plaintext password against which
        to check.
        @type password: L{six.text_type}
        @return: C{True} if the credentials represented by this object
        match the given password, C{False} if they do not, or a
        L{Deferred} which will be called back with one of these values.
        @rtype: L{bool} or L{twisted.web.defer.Deferred}
        """
        pass


class IWebAuthPermission(Interface):
    """
    This Interfaces encapsulates the permissions of a website to use
    this cross site auth.
    
    @ivar callback_url: the callback url
    @type callback_url: L{six.text_type}
    """
    def userdata_to_dict(userdata):
        """
        Transform the userdata into a dictionary which will be transmitted to the website.
        This method is part of this class so you can 'clean'/restrict what userdata which
        webseite will be allowed to access.
        
        @param userdata: userdata to clean
        @type userdata: L{IUserData}
        @return: the 'cleaned' dict
        @rtype: L{dict}
        """
        pass


class ILoginResource(Interface):
    """
    This interface is describes a resource used for the login.
    
    While this interface is named like a
    L{twisted.web.resource.IResource} and it is very similiar to it,
    there a few differences. Mainly, it is way more restriced than an
    IResource. This resource does not support children, and it's render
    methods work differently. However, the use of L{six.text_type} and
    L{twisted.internet.defer.Deferred} as return types is better
    supported.
    """
    
    def render_loginpage(request):
        """
        Render a GET request to the loginpage.
        
        This method should result in a HTML page string (either binary
        or unicode) or a deferred. The resulting HTML page should give
        the user a form to login. This form should cause a POST to this
        resource. The POST parameters of the form will later be passed
        to L{ILoginResource.handle_login_response}.
        IMPORTANT: remember to add the C{ctoken} value to the parameters
        
        @param request: the request to the page
        @type request: L{twisted.web.server.Request}
        @return: the page content
        @rtype: L{six.binary_type} or L{six.text_type} or a 
            L{twisted.internet.defer.Deferred} firing with either of
            those types
        """
        pass
    
    def handle_login_response(params):
        """
        This method will be called to convert the parameters of the
        login POST request to L{twisted.cred.credentials.ICredentials}.
        
        @param params: the POST parameters (as unicode dict)
        @type params: L{dict} of L{six.text_type} => L{list} of
            L{six.text_type}
        @return: the credentials
        @rtype: L{twisted.cred.credentials.ICredentials}
        """
        pass
    
    def render_login_failed(request):
        """
        Render a HTML page as response to a failed login attempt.
        
        @param request: the request to the page
        @type request: L{twisted.web.server.Request}
        @return: the page content
        @rtype: L{six.binary_type} or L{six.text_type} or a 
            L{twisted.internet.defer.Deferred} firing with either of
            those types
        """
        pass
    
    def render_invalid_login(request):
        """
        Render a HTML page as response to an invalid login request.
        
        A login request is invalid if it is missing essential parameters.
        
        @param request: the request to the page
        @type request: L{twisted.web.server.Request}
        @return: the page content
        @rtype: L{six.binary_type} or L{six.text_type} or a 
            L{twisted.internet.defer.Deferred} firing with either of
            those types
        """
        pass


class ILoginCookie(Interface):
    """
    This is the interface for storing login information in a cookie.
    
    @ivar userdata: the userdata of this login
    @type userdata: L{dict}
    """
    pass


class IUserData(Interface):
    """
    This is the interface for storing user data.
    """
    pass
