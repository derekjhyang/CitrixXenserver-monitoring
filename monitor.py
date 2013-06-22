#!/usr/bin/env python2.4
from __future__ import division
import sys
import time
import XenAPI
#import numpy
import platform
#from XenAPI import xapi_local as XMLRPCProxy
from parse_rrd import RRDUpdates
from xml import sax


class ParamMatchError(Exception): pass



""" Here we use SAX to parse XML metric data (Current not in use)"""
class RRDContentHandler(sax.ContentHandler):
    """
       Xenserver performance metric data is in the format:
    <xport>
      <meta>
       <start>INTEGER</start>
       <step>INTEGER</step>
       <end>INTEGER</end>
       <rows>INTEGER</rows>
       <columns>INTEGER</columns>
       <legend>
        <entry>IGNOREME:(host|vm):UUID:PARAMNAME</entry>
        ... another COLUMNS-1 entries ...
       </legend>
      </meta>
      <data>
       <row>
        <t>INTEGER(END_TIME)</t>  # end time
        <v>FLOAT</v>              # value
        ... another COLUMNS-1 values ...
       </row>
       ... another ROWS-2 rows
       <row>
        <t>INTEGER(START_TIME)</t>
        <v>FLOAT</v>
        ... another COLUMNS-1 values ...
       </row>
      </data>
    </xport>
    """

    def __init__(self, report):
        "report is saved and later updated by this object. report should contain defaults already"
        self.report = report
        self.in_start_tag = False
        self.in_step_tag = False
        self.in_end_tag = False
        self.in_rows_tag = False
        self.in_columns_tag = False
        self.in_entry_tag = False
        self.in_row_tag = False
        self.column_details = []
        self.row = 0


    def startElement(self, name, attrs):
        self.raw_text = ""
        if name == 'start':
            self.in_start_tag = True
        elif name == 'step':
            self.in_step_tag = True
        elif name == 'end':
            self.in_end_tag = True
        elif name == 'rows':
            self.in_rows_tag = True
        elif name == 'columns':
            self.in_columns_tag = True
        elif name == 'entry':
            self.in_entry_tag = True
        elif name == 'row':
            self.in_row_tag = True
            self.col = 0
        if self.in_row_tag:
            if name == 't':
                self.in_t_tag = True
            elif name == 'v':
                self.in_v_tag = True


    def endElement(self, name):
        if name == 'start':
            # This overwritten later if there are any rows
            self.report.start_time = int(self.raw_text)
            self.in_start_tag = False
        elif name == 'step':
            self.report.step_time = int(self.raw_text)
            self.in_step_tag = False
        elif name == 'end':
            # This overwritten later if there are any rows
            self.report.end_time = int(self.raw_text)
            self.in_end_tag = False
        elif name == 'rows':
            self.report.rows = int(self.raw_text)
            self.in_rows_tag = False
        elif name == 'columns':
            self.report.columns = int(self.raw_text)
            self.in_columns_tag = False
        elif name == 'entry':
            (_, objtype, uuid, paramname) = self.raw_text.split(':')
            # lookup the obj_report corresponding to this uuid, or create if it does not exist
            if not self.report.obj_reports.has_key(uuid):
                self.report.obj_reports[uuid] = ObjectReport(objtype, uuid)
            obj_report = self.report.obj_reports[uuid]
            # save the details of this column
            self.column_details.append(RRDColumn(paramname, obj_report))
            self.in_entry_tag = False
        elif name == 'row':
            self.in_row_tag = False
            self.row += 1
        elif name == 't':
            # Extract start and end time from row data as it's more reliable than the values in the meta data
            t = int(self.raw_text)
            # Last row corresponds to start time
            self.report.start_time = t
            if self.row == 0:
                # First row corresponds to end time
                self.report.end_time = t
            self.in_t_tag = False
        elif name == 'v':
            v = float(self.raw_text)
            # Find object report and paramname for this col
            col_details = self.column_details[self.col]
            obj_report = col_details.obj_report
            paramname = col_details.paramname
            # Update object_report
            obj_report.insert_value(paramname, index=0, value=v) # use index=0 as this is the earliest sample so far
            # Update position in row
            self.col += 1
            self.in_t_tag = False



class Monitor(object):
    def __init__(self, url, user, password, period=300, step=1):
        self.url = "https://"+url+":443"
        ### http login ###
        #self.session = XenAPI.Session(url)
        #self.session.xenapi.login_with_password(user,password)
        #self.xapi = self.session.xenapi

        ### local client proxy login ###
        self.session = XenAPI.xapi_local()
        self.session.login_with_password(user, password)     
        self.xapi = self.session.xenapi
        
        self.params = {}
        self.params['cf'] = 'AVERAGE' # consolidation function
        self.params['start'] = int(time.time()) - period
        self.params['interval'] = step # step
        self.params['end'] = self.params['start'] + period
        self.mon_period = period
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
        self.rrd_updates.refresh(self.session.handle, self.params, self.url) 

 
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
        self.rrd_updates.refresh(self.session.handle, self.params, self.url) 
        self.cpu_state = {}
        self.mem_state = {}
        self.net_state = {}
        self.disk_state = {}
        if hostname is None:
            self.hostname = platform.node()
        else:
            self.hostname = hostname
     

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
                for row in range(self.rrd_updates.get_nrows()):
                    epoch = self.rrd_updates.get_row_time(row)                    
                    data_val = str(self.rrd_updates.get_host_data(param, row))
                    #print "epoch: %s, data_val: %s" % (epoch, data_val)
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
        diskstat = {}
        return diskstat


    def get_host_current_load(self):    
        pass


            



def KBToBytes(size):
    return size*1024 


def BytesToMB(size):
    """ bytes converts to Mbytes, here we use left shift to determine it. """
    return size/(1<<20)


def sys_load(dataList):
    """ 
        here we use 'standard deviation' to determine whether the system load is balanced,
        where the sys_load value is small better.
    """
    #return numpy.std(dataList)
    pass

def exp_smoothing(dataList):
    """
        here we use 'exponential smoothing' to predict the next time period data value
    """
    pass



if __name__ == "__main__":
    url = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
    hostmon = HostMonitor(url, user, password)
    for vm_opaque_ref in hostmon.get_allAvailHostingVMOpaqueRef():
        vm_uuid = hostmon.xapi.VM.get_record(vm_opaque_ref).get('uuid')
        label = hostmon.xapi.VM.get_record(vm_opaque_ref).get('name_label')
        print vm_uuid, label
        vmmon = VMMonitor(url, user, password, vm_uuid)
        print vmmon.get_vm_data(use_time_meta=True)
        print vmmon.get_cpu()
        print vmmon.get_memory()
        print vmmon.get_network()
        print vmmon.get_disk()

