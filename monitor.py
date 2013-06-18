#!/usr/bin/env python2.4
import sys
import time
import XenAPI
from XenAPI import xapi_local as XMLRPCProxy
from parse_rrd import RRDUpdates

class Monitor(object):

    def __init__(self, url, user, password):
        self.params = {}
        self.url = url
        self.client_proxy = XMLRPCProxy() # XML-RPC client
        self.xapi_local = XenAPI.xapi_local()

        try:
            self.client_proxy.login_with_password(user, password)
            self.xapi = self.client_proxy.xenapi
            self.rrd_updates = RRDUpdates()
            self.params['cf'] = 'AVERAGE' # consolidation function
            self.params['start'] = int(time.time()) # monitor start time
            self.params['interval'] = 5 # monitor time-interval
            self.params['host'] = 'false'

            self.rrd_updates.refresh(self.xapi_local.handle, self.params, self.url) 
        
        finally:
            self.client_proxy.logout()

    def get_latest_xenserver_data(self,**kwargs):
        host_uuid = self.rrd_updates.get_host_uuid()
 
    def get_cpu(self):
        pass    
  
    def get_memory(self):
        memstat = []
   
    def get_network(self):
        pass

    def get_io(self):
        pass

if __name__ == "__main__":
    url = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
    mon = Monitor(url, user, password)
