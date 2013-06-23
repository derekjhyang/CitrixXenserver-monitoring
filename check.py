#!/usr/bin/python2.4
# Author: Danie van Zyl (https://github.com/pylonpower/nagios_check_scripts)
# Purpose:
# Use XenAPI library to gather stats for nagios. Can be used with ssh/nrpe.
# Use at own risk! Always test on test machines before going to production

import XenAPI
import parse_rrd
import sys, getopt
import time

class checkXAPI:
	def __init__(self):
		self.params = {}
		#self.url = "http://localhost"
		self.url = "https://140.115.14.13:443"
		self.x = XenAPI.xapi_local()
  
		try:
			self.x.login_with_password("root","pdclab")
			self.xapi = self.x.xenapi
			self.rrd_updates = parse_rrd.RRDUpdates()
			self.params['cf'] = "AVERAGE"
			self.params['start'] = int(time.time()) - 10
			self.params['interval'] = 5
			self.params['host'] = "true"

			self.rrd_updates.refresh(self.x.handle, self.params, self.url)
		finally:
			self.x.logout()

	def latest_host_data(self,**key):
		host_uuid = self.rrd_updates.get_host_uuid()
		v = []
		for k in key:
			if k == "cpu":
				cpu_num = key["cpu"]
				paramList = []
				for i in range(cpu_num):
					paramList.append("cpu"+str(i))
			if k == "memory":
				paramList = ["memory_total_kib","memory_free_kib"]
		
		for param in self.rrd_updates.get_host_param_list():
			if param in paramList:
				max_time=0
				data=""
				for row in range(self.rrd_updates.get_nrows()):
					epoch = self.rrd_updates.get_row_time(row)
					dv = str(self.rrd_updates.get_host_data(param,row))
					if epoch > max_time:
						max_time = epoch
						data = dv
				v.append(float(data))
		return v
	
	def get_exit_status(self,w,c,type):
		if type == "cpu":
			p = self.perc_load 
		elif type == "mem":
			p = self.perc_mem 
		#p = 60.0 
		e = ''
		if int(p) < w:
			e = 0
		elif int(p) > w and int(p) < c:
			e = 1
		elif int(p)> c:
			e = 2
		return e
		
	def get_memory(self):
		memstat = []
		mem = self.latest_host_data(memory="true")
		self.perc_mem = round((float(mem[0])-float(mem[1]))*100/ float(mem[0]))
		memstat.append(mem)
		memstat.append(self.perc_mem)
		return memstat

	def get_cpu(self):
		cpustat = []
		cpu = self.latest_host_data(cpu=len(self.xapi.host_cpu.get_all()))
		t=0
		for i in cpu:
			t+=float(i)
		self.perc_load=t*100/len(cpu)
		cpustat.append(self.perc_load)
		cpustat.append(len(cpu))
		return cpustat


	
def main(argv):
	type = ''
	warnlvl = ''
	critlvl = ''
	mfree = ''
	mtotal = ''
	exit_status=4
	try:
		opts, args = getopt.getopt(argv,"t:w:c:")
	except getopt.GetoptError:
		print 'check_xapi.py -t <cpu,memory>  -w int -c int'
		sys.exit(2)
	for opt, arg in opts:
		if opt in ("-t", "--type"):
			type = arg
		elif opt in ("-w", "--warn"):
			warnlvl = int(arg)
		elif opt in ("-c", "--crit"):
			critlvl = int(arg)
		else:
			assert False, "exception"

	#print warnlvl, " .... ", critlvl
	if warnlvl > critlvl:
		print "Warning level can't be larger than the critical level!"
		sys.exit(3)


	check = checkXAPI()
	if type == "mem":
		mem=check.get_memory()
		print "Memory: %s/%s (%s%% in use)" % ((mem[0][0]-mem[0][1]),mem[0][0],mem[1])
		exit_status=check.get_exit_status(warnlvl,critlvl,type)		
	if type == "cpu":
		cpu=check.get_cpu()
		print "CPU Load: %s%% of %s CPUs" % (cpu[0], cpu[1])
		exit_status=check.get_exit_status(warnlvl,critlvl,type)

	sys.exit(exit_status)

	
if __name__ == "__main__":
   		main(sys.argv[1:])
