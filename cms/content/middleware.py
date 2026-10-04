import ipaddress
from django.conf import settings


def client_ip(request):
    peer = request.META.get('REMOTE_ADDR')
    try:
        address = ipaddress.ip_address(peer)
        if any(address in network for network in settings.TRUSTED_PROXY_NETWORKS):
            # Caddy overwrites this header; public caller headers are never trusted.
            return str(ipaddress.ip_address(request.META.get('HTTP_X_ARCADIAN_CLIENT_IP', peer)))
    except ValueError:
        pass
    return peer


class ResponsePolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.path.startswith(('/admin/', '/api/')):
            response['Cache-Control'] = 'private, no-store'
            response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
