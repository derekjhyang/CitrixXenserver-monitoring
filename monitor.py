#!/usr/bin/env python
import sys
import XenAPI
from XenAPI import xapi_local as XMLRPCProxy
from parse_rrd import RRDUpdates

class Monitor(object):

    def __init__(self, url, user, password):
        self.params = {}
        self.url = url
        self.client_proxy = XMLRPCProxy() # XML-RPC client
        try:
            self.client_proxy.login_with_password(user, password)   
        finally:
            self.client_proxy.logout()
         

if __name__ == "__main__":
    url = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
    mon = Monitor(url, user, password)
    print mon
