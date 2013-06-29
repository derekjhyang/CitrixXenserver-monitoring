#!/usr/bin/env python2.4
from __future__ import division # for float division
import sys
import time
import math
import XenAPI
import platform
from XenAPI import xapi_local as XenXmlRPCProxy
from parse_rrd import RRDUpdates

class Monitor(object):
    def __init__(self, url, user, password, period=300, step=1):
        self.url = "https://"+url+":443"
        ### url session login ###
        # enable the following code section, we can login the other
        # xenserver host via https seesion
        #self.session = XenAPI.Session(url)
        #self.session.xenapi.login_with_password(user,password)
        #self.xapi = self.session.xenapi

        ### local client proxy login ###
        self.session = XenXmlRPCProxy()
        self.session.login_with_password(user, password)     
        self.xapi = self.session.xenapi
        
        ## Xenserver RRDs query parameter settings ##
        self.params = {}
        self.params['cf'] = 'AVERAGE' # consolidation function: MIN/MAX/AVERAGE/LAST
        self.params['start'] = int(time.time()) - period # start time
        self.params['interval'] = step # step
        self.params['end'] = self.params['start'] + period # end time
        self.mon_period = period # monitor time period
        self.rrd_updates = RRDUpdates()
   
    def get_cpu(self):
        pass

    def get_memory(self):
        pass

    def get_network(self):
        pass

    def get_disk(self):
        pass 



class VMMonitor(Monitor):

    def __init__(self, url, user, password, uuid):
        super(VMMonitor, self).__init__(url, user, password)
        self.vm_uuid = uuid

        # do rrdtool refresh 
        self.rrd_updates.refresh(self.session.handle, self.params, self.url) 

        # each resource data point set which used to feed statistics information
        # to RRDtools
        self.statistics = {}
       
 
    def get_vm_data(self, key=None, use_time_meta=False): 
        vm = {}       
        for param in self.rrd_updates.get_vm_param_list(self.vm_uuid, key):
            if param != "":
                """ here we gather the last time-point data"""
                max_time = 0.0
                data = ""
                #print "number of rows: %s" % self.rrd_updates.get_nrows()
                for row in range(self.rrd_updates.get_nrows()):
                    epoch = self.rrd_updates.get_row_time(row)
                    data_val = str(self.rrd_updates.get_vm_data(self.vm_uuid, param, row))
                    #print "time: %s, data_val: %s" % (time.localtime(epoch),data_val)
                    if epoch > max_time:
                        max_time = epoch
                        data = data_val
                if use_time_meta:
                    vm['max_timestamp'] = max_time
                    vm['max_time'] = time.strftime("%H:%M:%S", time.localtime(max_time))
                vm[param] = data 
       
        if use_time_meta:
            vm['start_timestamp'] = self.params['start']
            vm['end_timestamp'] = self.params['end']
            vm['start_time'] = time.strftime("%H:%M:%S", time.localtime(self.params['start']))
            vm['end_time'] = time.strftime("%H:%M:%S", time.localtime(self.params['end']))
            vm['period'] = self.params['end'] - self.params['start']
        
        return vm


    def get_cpu(self):
        cpustat = {}
        #cpu_params = self.rrd_updates.get_vm_param_dict(self.vm_uuid,'cpu') 
        cpu_param_dict = self.get_vm_data('cpu')
        cpustat['vcpu_num'] = len(cpu_param_dict)
        val = 0.0
        nrows = self.rrd_updates.get_nrows() # row amount
        #print "number of rows: %s" % nrows
        for row in range(nrows):
            for param in cpu_param_dict:
                val += self.rrd_updates.get_vm_data(self.vm_uuid, param, row)
                #print "param: %s, val: %s" % (param, val) 
        #print val    
        cpustat['vcpu_utilization'] = val/(cpustat['vcpu_num']*nrows)
        return cpustat


    def get_memory(self):
        """ unit: bytes """
        memstat = {}
        mem_param_dict = self.get_vm_data('memory')
        #print mem_param_dict
        
        """
             0 <= memory_static_min <= memory_dynamic_min <= memory_dynamic_max <= memory_static_max
        """
        vm_ref = self.xapi.VM.get_by_uuid(self.vm_uuid)
        # static part
        memstat['memory_static_min'] = int(self.xapi.VM.get_record(vm_ref).get('memory_static_min'))
        memstat['memory_static_max'] = int(self.xapi.VM.get_record(vm_ref).get('memory_static_max'))
        # dynamic part
        memstat['memory_dynamic_min'] = int(self.xapi.VM.get_record(vm_ref).get('memory_dynamic_min'))
        memstat['memory_dynamic_max'] = int(self.xapi.VM.get_record(vm_ref).get('memory_dynamic_max'))
                
        memstat['total_memory'] = float(mem_param_dict['memory'])
        if mem_param_dict.has_key('memory_internal_free'):
            memstat['free_memory'] = float(mem_param_dict['memory_internal_free'])*1024
            memstat['used_memory'] = memstat['total_memory'] - memstat['free_memory'] 
            memstat['memory_utilization'] = memstat['used_memory']/memstat['total_memory']
        return memstat

 
    def get_network(self):
        netstat = {}
        net_param_dict = self.get_vm_data('vif')
        if len(net_param_dict):
            netstat.update(net_param_dict)
        #print net_param_dict
        import re
        rx_re_pattern = re.compile('vif_[0-9]_rx')
        tx_re_pattern = re.compile('vif_[0-9]_tx')
        rx_total = 0
        tx_total = 0
        for k,v in net_param_dict.iteritems():
            if rx_re_pattern.match(k):
                rx_total += float(v)
            elif tx_re_pattern.match(k):
                tx_total += float(v)
            #else:
            #    raise ParamMatchError("Param Match Error: "+k)
        #print rx_total, tx_total
        netstat['vif_rx_total'] = rx_total
        netstat['vif_tx_total'] = tx_total
        netstat['avg_vif_rx_rate'] = netstat['vif_rx_total']/self.mon_period # avg rx rate (bytes/sec)
        netstat['avg_vif_tx_rate'] = netstat['vif_tx_total']/self.mon_period # avg tx rate (bytes/sec)
        return netstat


    def get_disk(self):
        diskstat = {}
        disk_param_dict = self.get_vm_data('vbd')
        #print disk_param_dict
        import re
        read_pattern = re.compile('vbd_(.)+_read')
        write_pattern = re.compile('vbd_(.)+_write')
        disk_read_total_bytes = 0.0
        disk_write_total_bytes = 0.0
        for k,v in disk_param_dict.iteritems():
            if re.match(read_pattern, k):
                disk_read_total_bytes += float(v)
            elif re.match(write_pattern, k):
                disk_write_total_bytes += float(v)
            #else: 
            #    raise ParamMatchError("Param Match Error: "+k)
        #print disk_read_total_bytes, disk_write_total_bytes
        diskstat['vbd_read_total'] = disk_read_total_bytes
        diskstat['vbd_write_total'] = disk_write_total_bytes
        diskstat['avg_vbd_read_rate'] = diskstat['vbd_read_total']/self.mon_period
        diskstat['avg_vbd_write_rate'] = diskstat['vbd_write_total']/self.mon_period
        return diskstat



class HostMonitor(Monitor):

    def __init__(self, url, user, password, hostname=None):
        super(HostMonitor,self).__init__(url, user, password)
        self.cpu_state = {}
        self.mem_state = {}
        self.net_state = {}
        self.disk_state = {}
        # if we not provide the Xenserver host we want to monitor,
        # it can retrieve its hostname here.
        if hostname is None:
            self.hostname = platform.node()
        else:
            self.hostname = hostname

        # each resource data point set which used to feed statistics information
        # to RRDtools
        self.__statistics = {} # here we gather host resource statistics info.
        # update rrd
        self.rrd_updates.refresh(self.session.handle, self.params, self.url) 
  

    def get_allAvailHostingVMOpaqueRef(self):
        host_opaque_ref = "".join(self.xapi.host.get_by_name_label(self.hostname))
        if host_opaque_ref == "":
            return []
        else:
            return self.xapi.host.get_record(host_opaque_ref).get('resident_VMs')


    def get_host_data(self, key=None):
        host = {}
        for param in self.rrd_updates.get_host_param_list(key):
            if param != "":
                #print "host param: %s" % param
                max_time = 0.0   
                data = ""
                self.__statistics[param] = []  # here we use list to collect data-points
                for row in range(self.rrd_updates.get_nrows()):
                    epoch = self.rrd_updates.get_row_time(row)                    
                    data_val = str(self.rrd_updates.get_host_data(param, row))
                    print "row: %s, epoch: %s, param: %s, data_val: %s" % (row, epoch, param, data_val)
                    self.__statistics[param].append((epoch, data_val))
                    if epoch > max_time:
                        max_time = epoch
                        data = data_val
                host[param] = data
                #print "host_max_time: %s, host_max_data: %s" %(max_time, data)
        return host


    def get_cpu(self):
        cpustat = {}
        cpu_param_dict = self.get_host_data('cpu')
        #print cpu_param_dict
        cpustat['cpu_num'] = len(cpu_param_dict)
        val = 0.0
        nrows = self.rrd_updates.get_nrows()
        for row in range(nrows):
            for param in cpu_param_dict:
                val += self.rrd_updates.get_host_data(param, row)
        #print val
        cpustat['cpu_utilication'] = val/(cpustat['cpu_num']*nrows)
        self.cpu_state = cpustat
        return cpustat


    def get_memory(self):
        memstat = {}       
        mem_param_dict = self.get_host_data('memory')
        #print mem_param_dict
        memstat['total_memory'] = float(mem_param_dict['memory_total_kib'])
        memstat['free_memory'] = float(mem_param_dict['memory_free_kib'])
        memstat['used_memory'] = memstat['total_memory'] - memstat['free_memory']
        memstat['memory_utilization'] = memstat['used_memory']/memstat['total_memory'] 
        self.mem_stat = memstat
        return memstat


    def get_network(self):
        netstat = {}
        net_param_dict = self.get_host_data('pif_xenbr')
        #print net_param_dict
        xenbr_rx_total = 0.0
        xenbr_tx_total = 0.0
        for k,v in net_param_dict.iteritems():
            if k.endswith('rx'):
                xenbr_rx_total += float(v)
            elif k.endswith('tx'):
                xenbr_tx_total += float(v)
        #print xenbr_rx_total, xenbr_tx_total
        netstat['xenbr_rx_total'] = xenbr_rx_total
        netstat['xenbr_tx_total'] = xenbr_tx_total
        netstat['avg_xenbr_tx_rate'] = netstat['xenbr_tx_total']/self.mon_period
        netstat['avg_xenbr_rx_rate'] = netstat['xenbr_rx_total']/self.mon_period
        self.net_state = netstat 
        return netstat


    def get_disk(self):
        #diskstat = {}
        #return diskstat
        pass

   
    def get_statistics(self):
        return self.__statistics


    def get_host_current_load(self): 
        pass


def KBToBytes(size):
    return size*1024 


def BytesToMB(size):
    """ bytes converts to Mbytes, here we use left shift to determine it. """
    return size/(1<<20)


def sys_load(list):
    """ 
        here we use 'standard deviation' to determine whether the system load is balanced,
        where the sys_load value is small better.
    """
    avg = sum(list)/float(len(list))
    return math.sqrt(sum(map(lambda x: (x-avg)**2,list))/len(list))  


def ema(list, alpha=None):
    """
       here we use 'exponential moving average' to predict the next time period data value
    # EMA Formula: 

         X(0),X(1),X(2),...,X(t-1) : data-sets total with "t" time-period-points

         EMA(1) = X(0) // initial point            -> 1 terms
         EMA(2) = EMA(1) + alpha*(X(1)-EMA(1)) 
                = alpha*[X(1)] + (1-alpha)*X(0)    -> 2 terms
         EMA(3) = EMA(2) + alpha*[X(2)-EMA(2)] 
                = [alpha*X(1)+(1-alpha)*X(0)] + alpha*[X(2)-(alpha*X(1)+(1-alpha)*X(0))]
                = alpha*[X(2)+(1-alpha)*X(1)] + (1-alpha-alpha-alpha^2)*X(0)
                = alph*[X(2)+(1-alpha)*X(1)] + (1-alpha)^2*X(0)     -> 3 terms
           .
           .
         EMA(t) = alpha*X(t-1) + (1-alpha)*EMA(t-1) = EMA(t-1) + alpha*[X(t-1) - EMA(t-1)]
                  = ...
                                    1st               2nd                     3rd                            (t-1)-th
                  = alpha*[ (1-alpha)^(0)*X(t-1) + (1-alpha)^(1)*X(t-2) + (1-alpha)^(2)*X(t-3) + ...+ (1-alpha)^(t-2)*X(t-(t-1)) ]
                            t-th
                    + (1-alpha)^(t)*X(0)

         alpha = 1 /(number of data-points)
  
         where alpha: smoothing factor 
               X(t-1) is observation value at time (t-1) period           
               EMA(t-1) is prediction value at time (t-1) periods
               EMA(t) is prediction value at time t periods
    """
    ema_data = []
    
    # reversed order for the whole list (big->small)
    rev_list = sorted(list,reverse=True)
    
    if not alpha:
       alpha = 1/len(rev_list) # defaults 
    if (alpha<0) or (alpha>1):
       raise ValueError("0 < smoothing factor <= 1")
    
    alpha_bar = float(1-alpha)
    
    num_terms_list = [rev_list[:i] for i in range(1,len(rev_list)+1)]
    #print num_terms_list
    for nterms in num_terms_list:
        # calculate 1st~(t-1)-th terms corresponding exponential factor
        pre_exp_factor = [ alpha_bar**(i-1) for i in range(1,len(nterms))]
        # calculate the ema at the next time periods
        #ema_data.append( alpha*sum(map(lambda a,b: a*b, pre_exp_factor, nterms[:-1])) + \
        #                 (alpha_bar**len(nterms))*nterms[-1])
        ema_data.append(alpha*float(sum(float(a)*float(b) for a,b in zip(tuple(pre_exp_factor), tuple(nterms[:-1])))) + \
                         (alpha_bar**len(nterms))*float(nterms[-1]))
    return sorted(ema_data)



if __name__ == "__main__":
    
    if len(sys.argv) < 5:
        print 'usage: ./monitor.py <host> <user> <password> <type>'
        sys.exit()

    url = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
        
    data_type = sys.argv[4]
    
    hostmon = HostMonitor(url, user, password)
    
    if data_type == 'vm-list':
        monData = {}
        for vm_opaque_ref in hostmon.get_allAvailHostingVMOpaqueRef():
            vm_uuid = hostmon.xapi.VM.get_record(vm_opaque_ref).get('uuid')
            label = hostmon.xapi.VM.get_record(vm_opaque_ref).get('name_label')
            monData[vm_uuid] = label            
        print monData
    elif data_type == 'cpu':
        for vm_opaque_ref in hostmon.get_allAvailHostingVMOpaqueRef():
            vm_uuid = hostmon.xapi.VM.get_record(vm_opaque_ref).get('uuid')
            label = hostmon.xapi.VM.get_record(vm_opaque_ref).get('name_label')
            vmmon = VMMonitor(url, user, password, vm_uuid)
            monData = vmmon.get_cpu()
            monData['uuid'] = vm_uuid
            monData['label'] = label
            print monData
    elif data_type == 'memory':
        for vm_opaque_ref in hostmon.get_allAvailHostingVMOpaqueRef():
            vm_uuid = hostmon.xapi.VM.get_record(vm_opaque_ref).get('uuid')
            label = hostmon.xapi.VM.get_record(vm_opaque_ref).get('name_label')
            vmmon = VMMonitor(url, user, password, vm_uuid)
            monData = vmmon.get_memory()
            monData['uuid'] = vm_uuid
            monData['label'] = label
            print monData
    elif data_type == 'network':
        for vm_opaque_ref in hostmon.get_allAvailHostingVMOpaqueRef():
            vm_uuid = hostmon.xapi.VM.get_record(vm_opaque_ref).get('uuid')
            label = hostmon.xapi.VM.get_record(vm_opaque_ref).get('name_label')
            vmmon = VMMonitor(url, user, password, vm_uuid)            
            monData = vmmon.get_network()
            monData['uuid'] = vm_uuid
            monData['label'] = label
            print monData
    else:
        print 'invalid monitor type.'
    
    #print hostmon.get_cpu()
    #print hostmon.get_memory()
    #for vm_opaque_ref in hostmon.get_allAvailHostingVMOpaqueRef():
    #    vm_uuid = hostmon.xapi.VM.get_record(vm_opaque_ref).get('uuid')
    #    label = hostmon.xapi.VM.get_record(vm_opaque_ref).get('name_label')
    #    print vm_uuid, label
    #    vmmon = VMMonitor(url, user, password, vm_uuid)
    #    print vmmon.get_vm_data(use_time_meta=True)
    #    print vmmon.get_cpu()
    #    print vmmon.get_memory()
    #    print vmmon.get_network()
    #    print vmmon.get_disk()
    #    print "\n\n"
    #print ema(range(1,10))
