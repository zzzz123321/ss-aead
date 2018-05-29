#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import time
import sys
import os
import psutil
import configloader
import importloader
import cymysql
import subprocess
import socket
from shadowsocks import common, shell

class Nettest(object):

	def __init__(self):
		import threading
		self.event = threading.Event()
		self.has_stopped = False

	def nettest_thread(self):
		if self.event.wait(1):
			return

		logging.info("Nettest starting...You can't stop right now!")

		if configloader.get_config().MYSQL_SSL_ENABLE == 1:
			conn = cymysql.connect(
				host=configloader.get_config().MYSQL_HOST,
				port=configloader.get_config().MYSQL_PORT,
				user=configloader.get_config().MYSQL_USER,
				passwd=configloader.get_config().MYSQL_PASS,
				db=configloader.get_config().MYSQL_DB,
				charset='utf8',
				ssl={
					'ca': configloader.get_config().MYSQL_SSL_CA,
					'cert': configloader.get_config().MYSQL_SSL_CERT,
					'key': configloader.get_config().MYSQL_SSL_KEY})
		else:
			conn = cymysql.connect(
				host=configloader.get_config().MYSQL_HOST,
				port=configloader.get_config().MYSQL_PORT,
				user=configloader.get_config().MYSQL_USER,
				passwd=configloader.get_config().MYSQL_PASS,
				db=configloader.get_config().MYSQL_DB,
				charset='utf8')
		conn.autocommit(True)

		def speed():
			rx0 = 0; tx0 = 0; rx1 = 0; tx1 = 0
			for name, stats in psutil.net_io_counters(pernic=True).items():
				if name == "lo" or name.find("tun") > -1:
					continue
				rx0 += stats.bytes_recv
				tx0 += stats.bytes_sent
			time.sleep(1)
			for name, stats in psutil.net_io_counters(pernic=True).items():
				if name == "lo" or name.find("tun") > -1:
					continue
				rx1 += stats.bytes_recv
				tx1 += stats.bytes_sent
			speed1=[]
			speed1.append(rx1 - rx0)
			speed1.append(tx1 - tx0)
			return speed1

		def list2str(n):
			testlist = ""
			i = 0
			for r in n:
				if i == 0:
					testlist = str(r)
				elif i <= len(n):
					testlist += " " + str(r)
				i += 1
			return testlist

		def gettcping(ip_port):
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			t_start = round(time.time()*1000)
			try:
				s.settimeout(1)
				s.connect(ip_port)
				s.shutdown(socket.SHUT_RD)
				t_end = round(time.time()*1000)
				s.settimeout(None)
				return str(t_end-t_start)+"ms"
			except Exception as e:
				s.settimeout(None)
				return "timeout"

		def getmyping(ip):
			laytency = subprocess.Popen(["ping -c 1 " + ip + ' | grep "time="'], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
			try:
				stdout, stderr = laytency.communicate(timeout=2)
				stdout = str(stdout).split("=")[3].replace("\\n","").replace(" ","").replace("'","")
				return stdout
			except subprocess.TimeoutExpired as e:
				laytency.kill()
				return "timeout"

		def getpinglist():
			cur = conn.cursor()
			cur.execute("SELECT `id`,`ip` FROM `test_ip` where `ip` != ''")
			n=[]
			for r in cur.fetchall():
				r = list(r)
				n.append(r[0])
				n.append(getmyping(r[1]))
			cur.close()
			return n

		def gettcpinglist():
			cur = conn.cursor()
			cur.execute("SELECT `id`,`ip`,`port` FROM `test_ip` where `ip` != ''")
			n=[]
			for r in cur.fetchall():
				r = list(r)
				n.append(r[0])
				n.append(gettcping( (r[1],int(r[2])) ))
			cur.close()
			return n

		cur = conn.cursor()
		cur.execute("INSERT INTO `ss_node_net_info` (`id`, `node_id`, `up`, `dl`, `ping`, `log_time`) VALUES (NULL, '" + str(configloader.get_config().NODE_ID) + "', '" + str(speed()[0]) + "', '" + str(speed()[1]) + "', '" + list2str(gettcpinglist()) + "', unix_timestamp()); ")
		cur.close()
		conn.close()

		logging.info("Nettest finished")

	@staticmethod
	def thread_db(obj):

		if configloader.get_config().NETTEST == 0:
			return

		if configloader.get_config().API_INTERFACE == 'modwebapi':
			import webapi_utils

			global webapi
			webapi = webapi_utils.WebApi()

		global db_instance
		db_instance = obj()

		try:
			while True:
				try:
					db_instance.nettest_thread()
				except Exception as e:
					import traceback
					trace = traceback.format_exc()
					logging.error(trace)
					#logging.warn('db thread except:%s' % e)
				if db_instance.event.wait(configloader.get_config().NETTEST*60):
					break
				if db_instance.has_stopped:
					break
		except KeyboardInterrupt as e:
			pass
		db_instance = None

	@staticmethod
	def thread_db_stop():
		global db_instance
		db_instance.has_stopped = True
		db_instance.event.set()
