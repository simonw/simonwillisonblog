from django.core.management.base import BaseCommand
import requests
import os

urls = (
    'https://www.cloudflare.com/ips-v4',
    'https://www.cloudflare.com/ips-v6',
)
filepath = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    '../ip_ranges.py'
)


class Command(BaseCommand):
    help = "Fetch Cloudflare IP addresses and save to disk"

    def handle(self, *args, **kwargs):
        ips = []
        for url in urls:
            ips.extend([
                ip.strip()
                for ip in requests.get(url).content.split('\n')
                if ip.strip()
            ])
        fp = open(filepath, 'w')
        fp.write(
            'from __future__ import unicode_literals\n'
            'import ipaddress\n\n'
            'IP_RANGES = [\n'
        )
        for ip in ips:
            fp.write("    ipaddress.ip_network('%s'),\n" % ip)
        fp.write(']\n')
