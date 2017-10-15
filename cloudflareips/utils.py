import ipaddress

try:
    from ip_ranges import IP_RANGES
except ImportError:
    IP_RANGES = []


def is_cloudflare(ip):
    ip_address = ipaddress.ip_address(unicode(ip))
    return any(r for r in IP_RANGES if ip_address in r)
