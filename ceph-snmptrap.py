#!/usr/bin/env python
# -*- coding: utf-8 -*- 

from librados import Client
from datetime import datetime
from exception import ExternalCommandError
import requests
import sys
import os
import configobj
import subprocess
import time
import sys
import salt.client
import six


def getCurrentTime():
    strTime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #strTime = datetime.now().strftime('%Y-%m-%d')
    return strTime

# run command line
def runCmd(command, timeout=10):
    proc = subprocess.Popen(command, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    poll_seconds = .250
    deadline = time.time()+timeout
    while time.time() < deadline and proc.poll() == None:
        time.sleep(poll_seconds)

    if proc.poll() == None:
        if float(sys.version[:3]) >= 2.6:
            proc.terminate()
        raise NotSupportedError()

    stdout, stderr = proc.communicate()
    return stdout, stderr, proc.returncode

# run salt command
def salt_cmd(tgt,
            fun,
            arg=(),
            timeout=None,
            expr_form='list',
            ret='',
            jid='',
            kwarg=None,
            **kwargs):
 
    local = salt.client.LocalClient()
    pub_data = local.run_job(tgt, fun, arg, expr_form, ret, timeout, jid, listen=True, **kwargs)
    
    if not pub_data:
        return pub_data
    ret = {}
    fn_rets = local.get_cli_event_returns(
                    pub_data['jid'],
                    pub_data['minions'],
                    timeout,
                    tgt,
                    expr_form,
                    **kwargs)


    for fn_ret in fn_rets:
        for mid, data in six.iteritems(fn_ret):
            ret[mid] = data

    for failed in list(set(pub_data['minions']) ^ set(ret.keys())):
        key = {}
        key["retcode"] = 1
        key["ret"] = "The Server or Salt minion is Down"
        ret[failed] = key
        
    return ret

def salt_cmd2(tgt,
            fun,
            arg=(),
            timeout=None,
            expr_form='list',
            ret='',
            jid='',
            kwarg=None,
            **kwargs):
 
    local = salt.client.LocalClient()
    pub_data = local.run_job(tgt, fun, arg, expr_form, ret, timeout, jid, listen=True, **kwargs)
    
    if not pub_data:
        return pub_data
    ret = {}
    for fn_ret in local.get_cli_event_returns(
                    pub_data['jid'],
                    pub_data['minions'],
                    timeout,
                    tgt,
                    expr_form,
                    **kwargs):

                if fn_ret:
                    for mid, data in six.iteritems(fn_ret):
                        ret[mid] = data.get('ret', {})

    for failed in list(set(pub_data['minions']) ^ set(ret.keys())):
        ret[failed] = False
        
    return ret

class CephSNMP:

    def __init__(self, client = None):
        self.client = client
        self.settings = self.getSetting()
        self.snmp_community = self.settings['SNMP_COMMUNITY']
        self.snmp_host = self.settings['SNMP_HOST']
        self.monAvalibeServer = None
        self.osdAvalibeServer = None
        self.igwAvalibeServer = None
    

    def getSetting(self):
        #local_settings_file = os.path.join(os.getcwd(), 'ceph-snmp.conf')
        local_settings_file = os.path.join(sys.path[0], 'ceph-snmp.conf')
        snmpsetting={}
        if os.access(local_settings_file, os.R_OK):
            for key, val in configobj.ConfigObj(local_settings_file).items():
                snmpsetting[key] = val

        return snmpsetting

    @staticmethod
    def _args_to_argdict(**kwargs):
        return {k: v for (k, v) in kwargs.iteritems() if v is not None}

    def getAlertDict(self,alarmType=""):
        alertDict = {"alarmInfo": "",
                     "alarmType":alarmType,
                     "alarmSeverity":"",
                     "alarmTime":"",
                     "alarmCause":"",
                     "isConfirmed":"",
                     "confirmTime":"",
                     "confirmUser":"",
                     "resourceId":"",
                     "resourceName":"",
                     "resourceType":"",
                     "metadata":""}

        return alertDict
        
    def postAlert(self,datas):
        return
        headers = {'Content-type': 'application/json'}
        timeout= 5
        postURL = self.settings["SNMPURL"]
        print datas
        rsp = requests.post(postURL, json=datas, headers=headers, timeout=timeout)
        print rsp
   
    # Ceph集群服务故障
    def clusterDisconnetted(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 101
        alertDict["alarmSeverity"] = 1
        alertDict["resourceType"] = "Cluster"
        alertDict["resourceName"] = "Ceph"
        alertDict["resourceId"] = ""
        if ex:
           alertDict["alarmCause"] = str(ex)
        alertDict["alarmInfo"] = "Ceph集群故障"
        self.postAlert(datas = alertDict)
        #print alertDict
        
    # Ceph集群服务正常，客户端网络连接问题
    def adminDisconnetted(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 102
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "Cluster"
        alertDict["resourceName"] = self.settings["ADMIN_SERVER"]
        alertDict["resourceId"] = ""
        if ex:
           alertDict["alarmCause"] = str(ex)
        alertDict["alarmInfo"] = "Ceph连接故障"
        self.postAlert(datas = alertDict)

    # Ceph集群健康状态非health
    def clusterStatus(self, ex = None, msg = ""):
        ceph_cmd = "health"
        argdict = self._args_to_argdict(detail = 'detail')
        retDict = self.client.mon_command(cmd=ceph_cmd,argdict=argdict)
        #print retDict
        status = retDict["status"]
        if status == "HEALTH_OK":
            return True
        
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 103
        alertDict["alarmSeverity"] = 3
        alertDict["resourceType"] = "Cluster"
        alertDict["resourceName"] = "Ceph"
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "Ceph集群健康状态异常"
        alertDict["alarmCause"] = str(retDict["summary"])
        
        self.postAlert(datas = alertDict)
        return False

    # 管理服务器故障关机、硬盘/网卡损坏
    def adminAlert(self, ex = None, msg=""):
       # TODO
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 201
        alertDict["alarmSeverity"] = 3
        alertDict["resourceType"] = "Admin"
        alertDict["resourceName"] = self.settings["ADMIN_SERVER"]
        alertDict["resourceId"] = ""
        alertDict["alarmCause"] = msg
        alertDict["alarmInfo"] =  "管理服务器故障"
        self.postAlert(datas = alertDict)

    # MON服务器故障: 关机、硬盘/网卡损坏
    def monServerAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 202
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "MON"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "MON服务器故障"
        alertDict["alarmCause"] = msg 
        monservers = self.settings["MON_SERVER"]
 
        # check if pingable
        servers = self.getAvailableMon()
        notpingableServers = self.getNotAvailableServers(servers,monservers)
        for server in notpingableServers:
            alertDict["resourceName"] = server
            #alertDict["alarmInfo"] = "Network problem"
            alertDict["alarmCause"]  = "Network problem: The server maybe is down"
            self.postAlert(datas = alertDict)
            alertDict["resourceName"] = ""
        
        

    # 存储服务器故障: 关机、硬盘/网卡损坏
    def osdServerAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 203
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "OSD"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "存储服务器故障"
        alertDict["alarmCause"] = msg 
        osdservers = self.settings["OSD_SERVER"]
 
        # check if pingable
        servers = self.getAvailableOsd()
        notpingableServers = self.getNotAvailableServers(servers,osdservers)
        for server in notpingableServers:
            alertDict["resourceName"] = server
            #alertDict["alarmInfo"] = "Network problem"
            alertDict["alarmCause"]  = "Network problem: The server maybe is down"
            self.postAlert(datas = alertDict)
            alertDict["resourceName"] = ""
        

    # ISCSI服务器故障: 关机、网卡损坏
    def iscsiServerAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 204
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "ISCSI"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "ISCSI服务器故障"
        alertDict["alarmCause"] = msg 
        iscsiservers = self.settings["IGW_SERVER"]
        servers = self.getAvailableIGW()
 
        # check if pingable
        notpingableServers = self.getNotAvailableServers(servers,iscsiservers)
        for server in notpingableServers:
            alertDict["resourceName"] = server
            #alertDict["alarmInfo"] = "Network problem"
            alertDict["alarmCause"]  = "Network problem: The server maybe is down"
            self.postAlert(datas = alertDict)
            alertDict["resourceName"] = ""
        

    # OSD节点离线: 单个盘离线
    def osdAlert(self, ex = None, msg = "", osdlist = None):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 301
        alertDict["alarmSeverity"] = 3
        alertDict["resourceType"] = "OSD"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "OSD节点离线"
        alertDict["alarmCause"] = msg 
        for osd in osdlist:
            if osd["status"] != "up":
                alertDict["resourceName"] = osd["name"]
                alertDict["resourceId"] = osd["id"]
                alertDict["alarmCause"] = str(osd["name"]) + " in " + str(osd["host"]) + " is " + str(osd["status"])
                self.postAlert(datas = alertDict)

    # OSD服务故障
    def osdStatus(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 302
        alertDict["alarmSeverity"] = 3
        alertDict["resourceType"] = "OSD"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "OSD服务故障"
        alertDict["alarmCause"] = msg 
        # TODO: same as OSD节点离线?
        #self.postAlert(datas = alertDict)

    # PUBLIC网络故障
    def pubNetAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 401
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "Network"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "PUBLIC网络故障"
        alertDict["alarmCause"] = msg 
        #print "check public network"
        servers = list(set(self.getAvailableMon() + self.getAvailableOsd() + self.getAvailableIGW()))
        #print "servers " + str(servers)
        if servers:
            cmd_line = 'ping -c 1 ' + self.settings["PUBLIC_GW"]
            retdict = salt_cmd(servers, 'cmd.run', [cmd_line])
            for mid, data in six.iteritems(retdict):
                retcode = data.get('retcode', 0)
                if retcode != 0:
                    alertDict["resourceName"] = mid
                    alertDict["alarmCause"] = data.get('ret',"")
                    self.postAlert(datas = alertDict)
                    
    # CLUSTER网络故障
    def clusterNetAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 402
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "Network"
        alertDict["resourceName"] = "Ceph"
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "CLUSTER网络故障"
        alertDict["alarmCause"] = msg 
        # check cluster network
        servers = self.getAvailableOsd()
        #print "servers " + str(servers)
        if servers:
            cmd_line = 'ping -c 1 ' + self.settings["CLUSTER_GW"]
            retdict = salt_cmd(servers, 'cmd.run', [cmd_line])
            for mid, data in six.iteritems(retdict):
                retcode = data.get('retcode', 0)
                if retcode != 0:
                    alertDict["resourceName"] = mid
                    alertDict["alarmCause"] = data.get('ret',"")
                    self.postAlert(datas = alertDict)
                    

    # 存储池故障
    def poolAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 501
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "Pool"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "存储池故障"
        alertDict["alarmCause"] = msg 
        #self.postAlert(datas = alertDict)

    # 存储池使用量告警: 资源池使用容量超过85%
    def poolUsageAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 502
        alertDict["alarmSeverity"] = 5
        alertDict["resourceType"] = "Pool"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "存储池使用量告警"
        alertDict["alarmCause"] = msg 

        dfDict = self.client.mon_command(cmd="df")
        pools = dfDict.get("pools",[])
        for pool in pools:
            percent_used = pool.get("stats",{}).get("percent_used",0)
            if percent_used > 0.85:
                poolname = pool.get("name","")
                alertDict["resourceName"] = poolname
                alertDict["alarmCause"] = poolname + " usage is " + str(percent_used)
                self.postAlert(datas = alertDict)


    # RBD故障
    def rbdAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 601
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "RBD"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "RBD故障"
        alertDict["alarmCause"] = msg 
        #self.postAlert(datas = alertDict)

    # RBD使用量告警: RBD使用容量超过85%
    def rbdUsageAlert(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 602
        alertDict["alarmSeverity"] = 5
        alertDict["resourceType"] = "RBD"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "RBD使用量告警"
        alertDict["alarmCause"] = msg 
        #self.postAlert(datas = alertDict)


    # ISCSI网关服务故障
    def iscsiStatus(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 701
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "ISCSI"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "ISCSI网关服务故障"
        alertDict["alarmCause"] = msg 

        servers = self.getAvailableIGW()
        #print "servers " + str(servers)
        if servers:
            cmd_line = 'systemctl status lrbd.service'
            retdict = salt_cmd(servers, 'cmd.run', [cmd_line])
            for mid, data in six.iteritems(retdict):
                retcode = data.get('retcode', 0)
                if retcode != 0:
                    alertDict["resourceName"] = mid
                    alertDict["alarmCause"] = data.get('ret',"")
                    self.postAlert(datas = alertDict)
                    
        #self.postAlert(datas = alertDict)

    # ISCSI target故障
    def iscsiError(self, ex = None, msg = ""):
        alertDict = self.getAlertDict()
        strTime = getCurrentTime()
        alertDict["alarmTime"] = strTime
        alertDict["alarmType"] = 702
        alertDict["alarmSeverity"] = 2
        alertDict["resourceType"] = "ISCSI"
        alertDict["resourceName"] = ""
        alertDict["resourceId"] = ""
        alertDict["alarmInfo"] = "ISCSI target故障"
        alertDict["alarmCause"] = msg 
        #self.postAlert(datas = alertDict)

    # 检查salt master状态
    def checkSaltStatus(self):
       cmd = ['systemctl', 'status', 'salt-master.service']
       stdout, stderr, returncode = runCmd(cmd)
       #print returncode
       return returncode == 0
       
       
    # 管理客户端是否链接
    def isAdminConnected(self):
       public_gw = self.settings["PUBLIC_GW"]
       if not self.isPingable(public_gw):
           #self.adminDisconnetted()
           return False
       return True
       
   
    def isPingable(self,server):
       cmd = ['ping','-c', '1',server]
       stdout, stderr, returncode = runCmd(cmd)
       if returncode != 0:
          return False
       return True

    def getAvailableServers(self,servers):
       ret = []
       for server in servers:
           if self.isPingable(server):
               ret.append(server)
       return ret

    def getNotAvailableServers(self,pingableservers,servers):
        ret = []
        #pingableservers = self.getAvailableServers(servers)
        for failed in list(set(pingableservers) ^ set(servers)):
            ret.append(failed)
        return ret

    def getAvailableMon(self):
        if not self.monAvalibeServer:
            self.monAvalibeServer = self.getAvailableServers(self.settings["MON_SERVER"])
        return self.monAvalibeServer

    def getAvailableOsd(self):
        if not self.osdAvalibeServer:
            self.osdAvalibeServer = self.getAvailableServers(self.settings["OSD_SERVER"])
        return self.osdAvalibeServer

    def getAvailableIGW(self):
        if not self.igwAvalibeServer:
            self.igwAvalibeServer = self.getAvailableServers(self.settings["IGW_SERVER"])
        return self.igwAvalibeServer


    # for SNMP TRAP
    def testsnmptrapNofity(self):
        self.snmptrapNofity(mibType = "cephNotificationCapacity", msg = "hello cephNotificationCapacity")
        self.snmptrapNofity(mibType = "cephNotificationStatus", msg = "hello cephNotificationStatus")
        self.snmptrapNofity(mibType = "cephNotificationRecovery", msg = "hello cephNotificationRecovery")
        self.snmptrapNofity(mibType = "cephNotificationNode", msg = "hello cephNotificationNode")
        self.snmptrapNofity(mibType = "cephNotificationDisk", msg = "hello cephNotificationDisk")
        self.snmptrapNofity(mibType = "cephNotificationNetwork", msg = "hello cephNotificationNetwork")
 
    # call snmptrap command to notify
    def snmptrapNofity(self, mibType = "", msg = ""):
        strTime = getCurrentTime()
        alertMsg = strTime + self.settings[mibType] + msg
        #cmdline = 'snmptrap -v 2c -c ' + self.snmp_community + ' ' + self.snmp_host +  ' "" CEPH-MIB::cephNotificationTrap CEPH-MIB::' + mibType + ' s ' +  alertMsg
        #print cmdline
        trapType = 'CEPH-MIB::' + mibType
        cmd = ['snmptrap', '-v', '2c', '-c', self.snmp_community, self.snmp_host, '', 'CEPH-MIB::cephNotificationTrap', trapType, 's', alertMsg]
        stdout, stderr, returncode = runCmd(cmd)
        if returncode != 0:
            print "Fail to snmp trap notify: " + stderr
        return returncode == 0
        
        
    # Ceph集群健康状态非health
    def clusterNofity(self, severity = "ERROR"):
        ceph_cmd = "health"
        argdict = self._args_to_argdict(detail = 'detail')
        retDict = self.client.mon_command(cmd=ceph_cmd,argdict=argdict)
        #print retDict
        status = retDict["status"]
        if status == "HEALTH_OK":
            return True
        
        if severity == "ERROR":
            # only notify error
            if status == "HEALTH_ERR":
                msg = "The cluster is in ERROR status!"
                self.snmptrapNofity(mibType = "cephNotificationStatus", msg = msg)
            return False
        
        msg = "The cluster is in " + status
        self.snmptrapNofity(mibType = "cephNotificationStatus", msg = msg)
        return True
        

    # MON服务器故障: 关机、硬盘/网卡损坏
    def monServerNotify(self):
        monservers = self.settings["MON_SERVER"]
 
        # check if pingable
        servers = self.getAvailableMon()
        notpingableServers = self.getNotAvailableServers(servers,monservers)
        if notpingableServers:
            msg = "The servers " + str(notpingableServers) + " is not pingable! "
            self.snmptrapNofity(mibType = "cephNotificationNode", msg = msg)
            
    # 存储服务器故障: 关机、硬盘/网卡损坏
    def osdServerNotify(self):
        osdservers = self.settings["OSD_SERVER"]
 
        # check if pingable
        servers = self.getAvailableOsd()
        notpingableServers = self.getNotAvailableServers(servers,osdservers)
        if notpingableServers:
            msg = "The servers " + str(notpingableServers) + " is not pingable! "
            self.snmptrapNofity(mibType = "cephNotificationNode", msg = msg)
        
    # ISCSI服务器故障: 关机、网卡损坏
    def iscsiServerNotify(self):
        iscsiservers = self.settings["IGW_SERVER"]
        servers = self.getAvailableIGW()
 
        # check if pingable
        notpingableServers = self.getNotAvailableServers(servers,iscsiservers)
        if notpingableServers:
            msg = "The servers " + str(notpingableServers) + " is not pingable! "
            self.snmptrapNofity(mibType = "cephNotificationNode", msg = msg)
        
    # OSD节点离线: 单个盘离线
    def osdNotify(self, osdlist = None):
        for osd in osdlist:
            if osd["status"] != "up":
                msg = str(osd["name"]) + " in " + str(osd["host"]) + " is " + str(osd["status"])
                self.snmptrapNofity(mibType = "cephNotificationDisk", msg = msg)

    # PUBLIC网络故障
    def pubNetNotify(self):
        #print "check public network"
        servers = list(set(self.getAvailableMon() + self.getAvailableOsd() + self.getAvailableIGW()))
        #print "servers " + str(servers)
        if servers:
            cmd_line = 'ping -c 1 ' + self.settings["PUBLIC_GW"]
            retdict = salt_cmd(servers, 'cmd.run', [cmd_line])
            for mid, data in six.iteritems(retdict):
                retcode = data.get('retcode', 0)
                if retcode != 0:
                    msg = "The server public network " + str(mid) + " is not pinable"
                    self.snmptrapNofity(mibType = "cephNotificationNetwork", msg = msg)
                    
    # CLUSTER网络故障
    def clusterNetNotify(self):
        # check cluster network
        servers = self.getAvailableOsd()
        #print "servers " + str(servers)
        if servers:
            cmd_line = 'ping -c 1 ' + self.settings["CLUSTER_GW"]
            retdict = salt_cmd(servers, 'cmd.run', [cmd_line])
            for mid, data in six.iteritems(retdict):
                retcode = data.get('retcode', 0)
                if retcode != 0:
                    msg = "The server cluster network " + str(mid) + " is not pinable"
                    self.snmptrapNofity(mibType = "cephNotificationNetwork", msg = msg)
                    
    # 存储池故障
    def poolNotify(self):
        # TODO
        pass

    # 存储池使用量告警: 资源池使用容量超过85%
    def poolUsageNotify(self):
        full_ratio = float(self.settings['POOL_FULL_RATIO'])
        dfDict = self.client.mon_command(cmd="df")
        pools = dfDict.get("pools",[])
        for pool in pools:
            percent_used = pool.get("stats",{}).get("percent_used",0)
            if percent_used > full_ratio:
                poolname = pool.get("name","")
                msg = poolname + " is near to full: " + str(percent_used)
                self.snmptrapNofity(mibType = "cephNotificationCapacity", msg = msg)


    # RBD故障
    def rbdNotify(self):
        pass

    # RBD使用量告警: RBD使用容量超过85%
    def rbdUsageNotify(self):
        pass


    # ISCSI网关服务故障
    def iscsiStatusNotify(self):
        servers = self.getAvailableIGW()
        #print "servers " + str(servers)
        if servers:
            cmd_line = 'systemctl status lrbd.service'
            retdict = salt_cmd(servers, 'cmd.run', [cmd_line])
            for mid, data in six.iteritems(retdict):
                retcode = data.get('retcode', 0)
                if retcode != 0:
                    msg = "The iSCSI service in servers " + str(mid) +  " is not starting! "
                    self.snmptrapNofity(mibType = "cephNotificationNode", msg = msg)
                    

    # ISCSI target故障
    def iscsiErrorNotify(self):
        pass

   
    # Cluster 数据无法恢复或者冗余度不够故障
    def dataAvailableNotify(self):
        ceph_cmd = "health"
        argdict = self._args_to_argdict(detail = 'detail')
        retDict = self.client.mon_command(cmd=ceph_cmd,argdict=argdict)
        #print retDict
        status = retDict["status"]
        if status == "HEALTH_OK":
            return 
        
        
        PG_AVAILABILITY = retDict.get("checks",{}).get('PG_AVAILABILITY',{})
        severity = PG_AVAILABILITY.get('severity','HEALTH_OK')
        message = PG_AVAILABILITY.get('summary',{}).get('message',"")
        if severity != "HEALTH_OK":
            msg = message
            self.snmptrapNofity(mibType = "cephNotificationRecovery", msg = msg)
        

    

        
if __name__=="__main__":
    client = None
    cephsnmp = None
    # check admin connection
    adminConnected = CephSNMP().isAdminConnected()
    if not adminConnected:
        msg = CephSNMP().setting['ADMIN_SERVER'] + " is not pingable!"
        print msg
        CephSNMP().snmptrapNofity(mibType = "cephNotificationNode", msg = msg)
        sys.exit(1)
    try:
        client = Client()
    except Exception as e:
        # 无法从admin 链接cluster
        msg = CephSNMP().settings['ADMIN_SERVER'] + " fails to connect cluster!"
        print msg
        CephSNMP().snmptrapNofity(mibType = "cephNotificationStatus", msg = msg)
        sys.exit(1)
    
    cephsnmp = CephSNMP(client)
    #print "testing snmp"
    #cephsnmp.testsnmptrapNofity()
    # clustser connected
    try:
       print "Connected to the cluster"
       print "Start to alert"
       print "check cluster"
       cephsnmp.clusterNofity()
       print "check data recovery issue"
       cephsnmp.dataAvailableNotify()
       print "salt_status"
       salt_status = cephsnmp.checkSaltStatus()

       print "check monitor server"
       cephsnmp.monServerNotify()

       print "check osd server"
       cephsnmp.osdServerNotify()

       print "check iscsi server"
       cephsnmp.iscsiServerNotify()

       print "check osd status"
       osdlist = client.osd_list()
       #print osdlist
       cephsnmp.osdNotify(osdlist = osdlist)

       print "check network"
       if salt_status:
           cephsnmp.pubNetNotify()
           cephsnmp.clusterNetNotify()

       print "check pool"
       cephsnmp.poolNotify()
       cephsnmp.poolUsageNotify()

       print "check rbd"
       cephsnmp.rbdNotify()
       cephsnmp.rbdUsageNotify()

       print "chechk iscsi"
       if salt_status:
           cephsnmp.iscsiStatusNotify()
           cephsnmp.iscsiErrorNotify()

    finally:
       print "closing cluster"
       client.disconnect()

