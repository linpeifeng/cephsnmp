copy all the scripts to SES admin node, e.g. /home/cephsnmp

1. modify the configuration file: ceph-snmp.conf according the SES nodes.
* configure SES information
* configure community and host ip of the SNMP server
  SNMP Server import MIB: CEPH-MIB.txt

2. run the scrip to test: /home/cephsnmp/ceph-snmptrap.py

3. run it in the crontab: crontab -e
*/5 * * * * /home/cephsnmp/ceph-snmptrap.py
