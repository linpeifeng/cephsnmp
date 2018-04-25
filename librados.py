
import logging
import json
import subprocess
import rados
import rbd
import six
from exception import ExternalCommandError

logger = logging.getLogger(__name__)

class Client(object):
    """Represents the connection to a single ceph cluster."""

    def __init__(self,timeout = 5):
        self._pools = {}
        """:type _pools: dict[str, rados.Ioctx]"""
        self._cluster = None
        """:type _cluster: rados.Rados"""
        self.conf="/etc/ceph/ceph.conf"
        self.keyring="/etc/ceph/ceph.keyring"
        self.cephcmd="/usr/bin/ceph"
        self._default_timeout = timeout
        self.connect()

    def get_pool(self, pool_name):
        if pool_name not in self._pools:
            self._pools[pool_name] = self._cluster.open_ioctx(pool_name)
        self._pools[pool_name].require_ioctx_open()

        return self._pools[pool_name]

    def connect(self, conf_file=""):
        if self._cluster is None:
            self._cluster = rados.Rados(conffile=self.conf)
            if self._default_timeout >= 0:
                timeout = six.text_type(self._default_timeout)
                self._cluster.conf_set('rados_osd_op_timeout', timeout)
                self._cluster.conf_set('rados_mon_op_timeout', timeout)
                self._cluster.conf_set('client_mount_timeout', timeout)

        if not self.connected():
            self._cluster.connect()

        return self._cluster

    def disconnect(self):
        for pool_name, pool in self._pools.items():
            if pool and pool.close:
                pool.close()

        if self.connected():
            self._cluster.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connected(self):
        return self._cluster and self._cluster.state == 'connected'

    def get_cluster_stats(self):
        return self._cluster.get_cluster_stats()

    def get_fsid(self):
        return self._cluster.get_fsid()

    def list_pools(self):
        return self._cluster.list_pools()

    def create_pool(self, pool_name, auid=None, crush_rule=None):
        return self._cluster.create_pool(pool_name, auid=auid, crush_rule=crush_rule)

    def pool_exists(self, pool_name):
        return self._cluster.pool_exists(pool_name)

    def delete_pool(self, pool_name):
        return self._cluster.delete_pool(pool_name)

    def get_stats(self, pool_name):
        return self.get_pool(pool_name).get_stats()

    def change_pool_owner(self, pool_name, auid):
        return self.get_pool(pool_name).change_auid(auid)

    def mon_command(self, cmd, argdict=None, output_format='json', default_return=None, target=None):
        """Calls a monitor command and returns the result as dict.

        If `cmd` is a string, it'll be used as the argument to 'prefix'. If `cmd` is a dict
        otherwise, it'll be used directly as input for the mon_command and you'll have to specify
        the 'prefix' argument yourself.

        :param cmd: the command
        :type cmd: str | dict[str, Any]
        :param argdict: Additional Command-Parameters
        :type argdict: dict[str, Any]
        :param output_format: Format of the return value
        :type output_format: str
        :param default_return: Return value in case of an error - if the answer given by Ceph cluster can't be Json
            decoded (only for output_format='json')
        :type default_return: any
        :return: Return type is json (aka dict) if output_format == 'json' else str.
        :rtype: str | dict[str, Any]

        :raises ExternalCommandError: The command failed with an error code instead of an exception.
        :raises PermissionError: See rados.make_ex
        :raises ObjectNotFound: See rados.make_ex
        :raises IOError: See rados.make_ex
        :raises NoSpace: See rados.make_ex
        :raises ObjectExists: See rados.make_ex
        :raises ObjectBusy: See rados.make_ex
        :raises NoData: See rados.make_ex
        :raises InterruptedOrTimeoutError: See rados.make_ex
        :raises TimedOut: See rados.make_ex
        """

        if type(cmd) is str:
            return self.mon_command(
                {'prefix': cmd}, argdict, output_format, default_return, target)

        elif type(cmd) is dict:
            (ret, out, err) = self._cluster.mon_command(
                json.dumps(dict(cmd,
                                format=output_format,
                                **argdict if argdict is not None else {})),
                '',
                timeout=self._default_timeout,
                target=target)
            logger.debug('mod command {}, {}, {}'.format(cmd, argdict, err))
            if ret == 0:
                if output_format == 'json':
                    if out:
                        return json.loads(out)
                    else:
                        logger.warning("Returned default value '{}' for command '{}' because the JSON object of the "
                                       "Ceph cluster's command output '{}' couldn't be decoded."
                                       .format(default_return, cmd, out))
                        return default_return
                return out
            else:
                raise ExternalCommandError(err, cmd, argdict, code=ret)

    def osd_list(self):
        """
        Info about each osd, eg "up" or "down".

        :rtype: list[dict[str, Any]]
        """
        def unique_list_of_dicts(l):
            return reduce(lambda x, y: x if y in x else x + [y], l, [])

        tree = self.osd_tree()
        nodes = tree['nodes']
        if 'stray' in tree:
            nodes += tree['stray']
        for node in nodes:
            if u'depth' in node:
                del node[u'depth']
        nodes = unique_list_of_dicts(nodes)
        osdlists = list(unique_list_of_dicts([node for node in nodes if node['type'] == 'osd']))
        hostlists = list(unique_list_of_dicts([node for node in nodes if node['type'] == 'host']))
        # add host info in osdlist
        for osdlist in osdlists:
            for hostlist in hostlists:
                if osdlist["id"] in hostlist["children"]:
                    osdlist["host"] = hostlist["name"]
                    break
        return osdlists

    def osd_tree(self):
        """Does not return a tree, but a directed graph with multiple roots.

        Possible node types are: pool. zone, root, host, osd

        Note, OSDs may be duplicated in the list, although the u'depth' attribute may differ between
        them.

        ..warning:: does not return the physical structure, but the crushmap, which will differ on
            some clusters. An osd may be physically located on a different host, than it is returned
            by osd tree.
        """
        return self.mon_command(cmd='osd tree')


class MonApi(object):
    
    def __init__(self, client):
        self.client = client
   
    def get_crushmap(self):
        crushmap = self.client.mon_command(cmd="osd crush dump")
        crushtree = dict(crushmap, buckets=[])

        devices = {}
        
        for device in crushmap["devices"]:
            devices[device["id"]] = device

        #print devices

        parentbucket = {}

        for cbucket in crushmap["buckets"]:

            for member in cbucket["items"]:
                #print member
                # Creates an array with all children using their IDs as keys and themselves as
                # values. This already excludes the root buckets!
                parentbucket[member["id"]] = cbucket
                #print parentbucket[member["id"]]
                
            #print cbucket

            # Clears the items of `crushmap['buckets']`.
            items = cbucket["items"][:]
            cbucket["items"] = []
           
            # add osd items
            if cbucket["type_name"] == "host":
                for member in items:
                    if type(member).__name__ == 'dict' and member.has_key("id"):
                        item = {}
                        item["name"] = devices[member["id"]]["name"]
                        cbucket["items"].append(devices[member["id"]])



        #print parentbucket

        buckets = crushmap["buckets"][:]  # Make a copy of the `buckets` array.
        while buckets:
            cbucket = buckets.pop(0)

            if cbucket["id"] in parentbucket:  # If the current bucket has a parent.

                # Add the child (cbucket) to the `items` array of the parent object.
                parentbucket[cbucket["id"]]["items"].append(cbucket)

            else:  # Has to be a root bucket.

                # Add the root bucket to the `buckets` array. It would be empty otherwise!
                crushtree["buckets"].append(cbucket)

        return crushtree


    def get_df(self):
        poolusages = self.client.mon_command(cmd="df")
        print poolusages
