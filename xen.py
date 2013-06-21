#!/usr/bin/python

#This is an example plugin for the popular network monitoring program nagios.

#Check if all the hosts in a pool are live.
#If we log in to a slave by mistake (the master can sometimes change)
#then redirect the request to the real master

#example command line: ./check_pool.py -H ivory -p password -l root

#So: return codes
# 0 : everything is ok
# 1 : named host is slave, but all hosts in pool are up
# 2 : some of the hosts in the pool are down
# 3 : unexpected error

#entire program wrapped in try/except so that we can send exit code 3 to nagios on any error

import XenAPI
import sys
import time
import urllib
import re
import traceback

from optparse import OptionParser
from pprint import pprint
from xml.dom import minidom


def formatExceptionInfo(maxTBlevel=5):
  cla, exc, trbk = sys.exc_info()
  excName = cla.__name__
  try:
    excArgs = exc.__dict__["args"]
  except KeyError:
    excArgs = "<no args>"
  excTb = traceback.format_tb(trbk, maxTBlevel)
  return (excName, excArgs, excTb)

def convertStr(s):
#Convert string to either int or float."""
  try:
    ret = float(s)
  except ValueError:
    #Try float.
    ret = int(s)
  return ret

def getLegendEntries(metaNode):
  count = 0;
  entries = [];

  if (metaNode.nodeName == 'meta') :
    for entrynode in metaNode.getElementsByTagName('legend'):
      for legendnode in entrynode.getElementsByTagName('entry'):
        for childnode in legendnode.childNodes:
          if (childnode.nodeType == childnode.TEXT_NODE):
            #print "childnode.data=%s" % childnode.data;
            entryelements =  re.split(":", childnode.data);
            entries.append("%s_%s" % (entryelements[1], entryelements[3]));
  return entries;

def getValueEntries(dataNode):
  count = 0;
  entries = [];

  if (dataNode.nodeName == 'data') :
    for rownode in dataNode.getElementsByTagName('row'):
      for valuenode in rownode.getElementsByTagName('v'):
        for childnode in valuenode.childNodes:
          if (childnode.nodeType == childnode.TEXT_NODE):
            #print "childnode.data=%s" % childnode.data;
            entries.append(childnode.data);
    return entries;


#Parse command line options
#Python's standard option parser won't do what I want, so I'm subclassing it.
#firstly, nagios wants exit code three if the options are bad
#secondly, we want 'required options', which the option parser thinks is an oxymoron.
#I on the other hand don't want to give defaults for the host and password, because nagios is difficult to set up correctly,
#and the effect of that may be to hide a problem.
 
class MyOptionParser(OptionParser):
    def error(self,msg):
      print msg
      sys.exit(3)
        #stolen from python library reference, add required option check
    def check_required(self, opt):
      option=self.get_option(opt)
      if getattr(self.values, option.dest) is None:
        self.error("%s option not supplied" % option)

try:

    parser = MyOptionParser(description="Nagios plugin to check whether all hosts in a pool are live")

    parser.add_option("-H", "--hostname", dest="hostname", help="name of pool master or slave")
    parser.add_option("-u", "--user-name", default="root", dest="username", help="name to log in as (usually root)")
    parser.add_option("-p", "--password", dest="password", help="password")
    parser.add_option("-L", "--license", default=False, dest="licensecheck", help="check XenServer License")
    parser.add_option("-I", "--info", default=False, dest="info", help="display XenServer info")
    parser.add_option("-w", "--warning", default="0", dest="warning", help="CPU % utilisation warning level")
    parser.add_option("-c", "--critical", default="0", dest="critical", help="CPU % utilisation critical level")

    (options, args) = parser.parse_args()

    #abort if host and password weren't specified explicitly on the command line
    parser.check_required("-H")
    parser.check_required("-p")


    #get a session. set host_is_slave true if we need to redirect to a new master
    host_is_slave=False
    try:
        session=XenAPI.Session('https://'+options.hostname)
        session.login_with_password(options.username, options.password)
    except XenAPI.Failure, e:
        if e.details[0]=='HOST_IS_SLAVE':
            session=XenAPI.Session('https://'+e.details[1])
            session.login_with_password(options.username, options.password)
            host_is_slave=True
        else:
            raise
    sx=session.xenapi


    #work out which hosts in the pool are alive, and which dead
    hosts=sx.host.get_all()
    hosts_with_status=[(sx.host.get_name_label(x),sx.host_metrics.get_live( sx.host.get_metrics(x) )) for x in hosts]

    live_hosts=[name for (name,status) in hosts_with_status if (status==True)]
    dead_hosts=[name for (name,status) in hosts_with_status if not (status==True)]

    # Pull out pertinent info about the host

    master_host = sx.session.get_this_host(session._session)
    if not host_is_slave:
      current_host = master_host
    else:
       for x in hosts:
         if (sx.host.get_address(x) == options.hostname):
           current_host=x
           break

    # get some info
    current_hostname = sx.host.get_hostname(current_host)

    # get enabled  - if its not enabled in the cluster, forget about the other info
    current_enabled = sx.host.get_enabled(current_host);

    # new steps to get the rrd export from the server!
    rrd_url = "http://%s/rrd_updates?start=%i&host=true&session_id=%s" % (sx.host.get_address(current_host), time.time()-20, session._session)
    #print "Fetching perf data from %s\n" % rrd_url
    dom = minidom.parse(urllib.urlopen(rrd_url))

    for node0 in dom.getElementsByTagName('xport'):
      for node1 in node0.getElementsByTagName('meta'):
        metricnames = getLegendEntries(node1)
      for node1 in node0.getElementsByTagName('data'):
        metricvalues = getValueEntries(node1) 

      # init our vars
      cpu_perf_warn = convertStr(options.warning)
      cpu_perf_crit = convertStr(options.critical)
      cpu_perf_msg = ""
      exitcode=0
      perf_data = ""
      i=0

      if(metricnames and metricvalues): 
       # pprint(metricnames);
       # pprint(metricvalues);
        while i < len(metricnames) : # loop through all our metrics
      #    print "metricnames[%s]\n" % (i)
      #    print "%s == '%s' metricnames[%s]\n" % (metricnames[i], metricvalues[i], i)
          # grab host entries
          if (re.match("host_cpu", metricnames[i])):
            #print "Host CPU entries: %s == '%s'\n" % (metricnames[i], metricvalues[i])
            if (convertStr(metricvalues[i]) >= cpu_perf_crit) and (convertStr(cpu_perf_crit) > 0 ):
                exitcode=2
                cpu_perf_msg += "!%s at %%%s! " % (metricnames[i],metricvalues[i])
            else:
              if (convertStr(metricvalues[i]) >= cpu_perf_warn) and (convertStr(cpu_perf_warn) > 0 ):
                cpu_perf_msg += "%s at %%%s " % (metricnames[i],metricvalues[i])
                if not (exitcode == 2) :
                  exitcode=1 

            perf_data += "'%s'=%s%%;%s;%s;0;100 " % (metricnames[i], metricvalues[i], cpu_perf_warn, cpu_perf_crit)

          else:
            if (re.match("host_", metricnames[i]) and not re.search("__tmp", metricnames[i])):
            # build a complete list of all the host metrics, yeah baby!
              perf_data += "'%s'=%s " % (metricnames[i], metricvalues[i])

          i += 1

    if(current_enabled):
      current_enabled_display = "Enabled" 

      #print session._session;
      #time.sleep(100)

      current_license = sx.host.get_license_params(current_host)
      if (options.licensecheck):
        # get this hosts license info
        pprint(current_license['serialnumber']) 
        pprint(current_license['version']) 
        pprint(current_license['expiry']) 
        pprint(current_license['productcode']) 

      # get this hosts name
      current_hostname = sx.host.get_hostname(current_host)

      # get resident VMs
      current_VMs = sx.host.get_resident_VMs(current_host) 
      current_VMs_running=[(sx.VM.get_name_label(x),sx.VM.get_record(x)) for x in current_VMs]
      current_running_hosts=[name for (name,vmgh) in current_VMs_running if (vmgh['power_state'] == 'Running') and not (vmgh['is_control_domain'])]
      current_paused_hosts=[name for (name,vmgh) in current_VMs_running if (vmgh['power_state'] == 'Paused')]
      display_status_vms="Resident VMs - Running: %i, Paused: %i" % (len(current_running_hosts), len(current_paused_hosts))
 
      
      if not (host_is_slave) : 
        #get total VMs counts
        vmg=sx.VM.get_all()
        #pprint(vmg);
        vmgs_running=[(sx.VM.get_name_label(x),sx.VM.get_record(x)) for x in vmg]
        #pprint(vmgs_running);
        running_hosts=[name for (name,vmgh) in vmgs_running if (vmgh['power_state'] == 'Running') and not (vmgh['is_control_domain'])]
        paused_hosts=[name for (name,vmgh) in vmgs_running if (vmgh['power_state'] == 'Paused')]
        actual_hosts=[name for (name,vmgh) in vmgs_running  if not (vmgh['is_a_template']) and not (vmgh['is_control_domain'])]
        display_status_vms+=", Pool VMs - Running: %s, Paused: %s, Total: %s" % (len(running_hosts), len(paused_hosts), len(actual_hosts))

    else:
      current_enabled_display="Disabled"
      exitcode=1
    #log out
    session.logout()

    if not (perf_data) :
        display_status_vms+=" Perf Stats unavailable, check XenServer settings"

    if (len(dead_hosts)<>0) :
      exitcode=2

    if(exitcode == 1):
      cpu_perf_msg = "WARN: " + cpu_perf_msg;
    if(exitcode == 2):
      cpu_perf_msg = "CRIT: " + cpu_perf_msg;

    #nagios wants a single line of output
    if (host_is_slave):
      print "SLAVE XS v%s %s (MASTER at %s) [%s] %s %s | %s" % (current_license['version'], current_hostname, e.details[1], current_enabled_display, cpu_perf_msg, display_status_vms, perf_data)
    else:
      print "MASTER XS v%s %s [%s] %s Live slaves %i dead slaves %i, %s | %s" % (current_license['version'], current_hostname, current_enabled_display, cpu_perf_msg, len(live_hosts), len(dead_hosts), display_status_vms, perf_data)

except Exception, e:
    print "Unexpected Exception "
    exctype, value = sys.exc_info()[:2]
    print formatExceptionInfo()
    sys.exit(3) #Nagios wants error 3 if anything weird happens

sys.exit(exitcode)
