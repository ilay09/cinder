# Copyright (c) 2012 - 2015 EMC Corporation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ast
import os
import shutil
import tempfile
import unittest
import uuid
from xml.dom import minidom

import ddt
import mock
from oslo_utils import units
import six

from cinder import exception
from cinder.i18n import _
from cinder.objects import consistencygroup
from cinder.objects import fields
from cinder.objects import qos_specs
from cinder import test
from cinder.tests.unit import fake_constants
from cinder.tests.unit import utils as unit_utils
from cinder import utils as cinder_utils

from cinder.volume import configuration as conf
from cinder.volume.drivers.dell_emc.vmax import common
from cinder.volume.drivers.dell_emc.vmax import fast
from cinder.volume.drivers.dell_emc.vmax import fc
from cinder.volume.drivers.dell_emc.vmax import iscsi
from cinder.volume.drivers.dell_emc.vmax import masking
from cinder.volume.drivers.dell_emc.vmax import provision
from cinder.volume.drivers.dell_emc.vmax import provision_v3
from cinder.volume.drivers.dell_emc.vmax import utils
from cinder.volume import volume_types

CINDER_EMC_CONFIG_DIR = '/etc/cinder/'
utils.JOB_RETRIES = 0
utils.INTERVAL_10_SEC = 0


class EMC_StorageVolume(dict):
    pass


class CIM_StorageExtent(dict):
    pass


class SE_InitiatorMaskingGroup(dict):
    pass


class SE_ConcreteJob(dict):
    pass


class SE_StorageHardwareID(dict):
    pass


class CIM_ReplicationServiceCapabilities(dict):
    pass


class SYMM_SrpStoragePool(dict):
    pass


class SYMM_LunMasking(dict):
    pass


class CIM_DeviceMaskingGroup(dict):
    pass


class EMC_LunMaskingSCSIProtocolController(dict):
    pass


class CIM_TargetMaskingGroup(dict):
    pass


class EMC_StorageHardwareID(dict):
    pass


class CIM_IPProtocolEndpoint(dict):
    pass


class Symm_ArrayChassis(dict):
    pass


class CIM_ConnectivityCollection(dict):
    pass


class SE_ReplicationSettingData(dict):
    def __init__(self, *args, **kwargs):
        self['DefaultInstance'] = self.createInstance()

    def createInstance(self):
        self.DesiredCopyMethodology = 0


class Fake_CIMProperty(object):

    def fake_getCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = True
        return cimproperty

    def fake_getBlockSizeCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = '512'
        return cimproperty

    def fake_getConsumableBlocksCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = '12345'
        return cimproperty

    def fake_getIsConcatenatedCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = True
        return cimproperty

    def fake_getIsCompositeCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = False
        return cimproperty

    def fake_getTotalManagedSpaceCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = '20000000000'
        return cimproperty

    def fake_getRemainingManagedSpaceCIMProperty(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = '10000000000'
        return cimproperty

    def fake_getElementNameCIMProperty(self, name):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = name
        return cimproperty

    def fake_getSupportedReplicationTypes(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.value = [2, 10]
        return cimproperty

    def fake_getipv4address(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.key = 'IPv4Address'
        cimproperty.value = '10.10.10.10'
        return cimproperty

    def fake_getiqn(self):
        cimproperty = Fake_CIMProperty()
        cimproperty.key = 'Name'
        cimproperty.value = (
            'iqn.1992-04.com.emc:600009700bca30c01b9c012000000003,t,0x0001')
        return cimproperty

    def fake_getSupportedReplicationTypesCIMProperty(self, reptypes):
        cimproperty = Fake_CIMProperty()
        if reptypes == 'V3':
            cimproperty.value = [6, 7]
        elif reptypes == 'V3_SYNC':
            cimproperty.value = [6]
        elif reptypes == 'V3_ASYNC':
            cimproperty.value = [7]
        elif reptypes == 'V2':
            cimproperty.value = [10]
        else:
            cimproperty.value = [2, 3, 4, 5]
        return cimproperty


class Fake_CIM_TierPolicyServiceCapabilities(object):

    def fake_getpolicyinstance(self):
        classinstance = Fake_CIM_TierPolicyServiceCapabilities()

        classcimproperty = Fake_CIMProperty()
        cimproperty = classcimproperty.fake_getCIMProperty()

        cimproperties = {u'SupportsTieringPolicies': cimproperty}
        classinstance.properties = cimproperties

        return classinstance


class FakeCIMInstanceName(dict):

    def fake_getinstancename(self, classname, bindings):
        instancename = FakeCIMInstanceName()
        for key in bindings:
            instancename[key] = bindings[key]
        instancename.classname = classname
        instancename.namespace = 'root/emc'
        return instancename


class FakeDB(object):

    def volume_update(self, context, volume_id, model_update):
        pass

    def volume_get(self, context, volume_id):
        conn = FakeEcomConnection()
        objectpath = {}
        objectpath['CreationClassName'] = 'Symm_StorageVolume'

        if volume_id == 'vol1':
            device_id = '1'
            objectpath['DeviceID'] = device_id
        else:
            objectpath['DeviceID'] = volume_id
        return conn.GetInstance(objectpath)

    def volume_get_all_by_group(self, context, group_id):
        volumes = []
        volumes.append(VMAXCommonData.test_source_volume)
        return volumes

    def consistencygroup_get(self, context, cg_group_id):
        return VMAXCommonData.test_CG

    def snapshot_get_all_for_cgsnapshot(self, context, cgsnapshot_id):
        snapshots = []
        snapshots.append(VMAXCommonData.test_snapshot)
        return snapshots


class VMAXCommonData(object):
    wwpn1 = "123456789012345"
    wwpn2 = "123456789054321"
    connector = {'ip': '10.0.0.2',
                 'initiator': 'iqn.1993-08.org.debian: 01: 222',
                 'wwpns': [wwpn1, wwpn2],
                 'wwnns': ["223456789012345", "223456789054321"],
                 'host': 'fakehost'}

    target_wwns = [wwn[::-1] for wwn in connector['wwpns']]

    fabric_name_prefix = "fakeFabric"
    end_point_map = {connector['wwpns'][0]: [target_wwns[0]],
                     connector['wwpns'][1]: [target_wwns[1]]}
    zoning_mappings = {'port_group': None,
                       'initiator_group': None,
                       'target_wwns': target_wwns,
                       'init_targ_map': end_point_map}
    device_map = {}
    for wwn in connector['wwpns']:
        fabric_name = ''.join([fabric_name_prefix,
                              wwn[-2:]])
        target_wwn = wwn[::-1]
        fabric_map = {'initiator_port_wwn_list': [wwn],
                      'target_port_wwn_list': [target_wwn]
                      }
        device_map[fabric_name] = fabric_map

    default_storage_group = (
        u'//10.10.10.10/root/emc: SE_DeviceMaskingGroup.InstanceID='
        '"SYMMETRIX+000198700440+OS_default_GOLD1_SG"')
    default_sg_instance_name = {
        'CreationClassName': 'CIM_DeviceMaskingGroup',
        'ElementName': 'OS_default_GOLD1_SG',
        'SystemName': 'SYMMETRIX+000195900551'}
    sg_instance_name = {
        'CreationClassName': 'CIM_DeviceMaskingGroup',
        'ElementName': 'OS-fakehost-SRP_1-Bronze-DSS-I-SG',
        'SystemName': 'SYMMETRIX+000195900551'}
    storage_system = 'SYMMETRIX+000195900551'
    storage_system_v3 = 'SYMMETRIX-+-000197200056'
    port_group = 'OS-portgroup-PG'
    port_group_instance = {'ElementName': 'OS-portgroup-PG'}
    lunmaskctrl_id = (
        'SYMMETRIX+000195900551+OS-fakehost-gold-I-MV')
    lunmaskctrl_name = (
        'OS-fakehost-gold-I-MV')
    mv_instance_name = {
        'CreationClassName': 'Symm_LunMaskingView',
        'ElementName': 'OS-fakehost-SRP_1-Bronze-DSS-I-Mv',
        'SystemName': 'SYMMETRIX+000195900551'}

    rdf_group = 'test_rdf'
    srdf_group_instance = (
        '//10.73.28.137/root/emc:Symm_RemoteReplicationCollection.'
        'InstanceID="SYMMETRIX-+-000197200056-+-8-+-000195900551-+-8"')
    rg_instance_name = {
        'CreationClassName': 'CIM_DeviceMaskingGroup',
        'ElementName': 'OS-SRP_1-gold-DSS-RE-SG',
        'SystemName': 'SYMMETRIX+000197200056'
    }

    initiatorgroup_id = (
        'SYMMETRIX+000195900551+OS-fakehost-IG')
    initiatorgroup_name = 'OS-fakehost-I-IG'
    initiatorgroup_creationclass = 'SE_InitiatorMaskingGroup'
    iscsi_initiator = 'iqn.1993-08.org.debian'
    storageextent_creationclass = 'CIM_StorageExtent'
    initiator1 = 'iqn.1993-08.org.debian: 01: 1a2b3c4d5f6g'
    stconf_service_creationclass = 'Symm_StorageConfigurationService'
    ctrlconf_service_creationclass = 'Symm_ControllerConfigurationService'
    elementcomp_service_creationclass = 'Symm_ElementCompositionService'
    storreloc_service_creationclass = 'Symm_StorageRelocationService'
    replication_service_creationclass = 'EMC_ReplicationService'
    vol_creationclass = 'Symm_StorageVolume'
    pool_creationclass = 'Symm_VirtualProvisioningPool'
    lunmask_creationclass = 'Symm_LunMaskingSCSIProtocolController'
    lunmask_creationclass2 = 'Symm_LunMaskingView'
    hostedservice_creationclass = 'CIM_HostedService'
    policycapability_creationclass = 'CIM_TierPolicyServiceCapabilities'
    policyrule_creationclass = 'Symm_TierPolicyRule'
    assoctierpolicy_creationclass = 'CIM_StorageTier'
    storagepool_creationclass = 'Symm_VirtualProvisioningPool'
    srpstoragepool_creationclass = 'Symm_SRPStoragePool'
    storagegroup_creationclass = 'CIM_DeviceMaskingGroup'
    hardwareid_creationclass = 'EMC_StorageHardwareID'
    replicationgroup_creationclass = 'CIM_ReplicationGroup'
    storagepoolid = 'SYMMETRIX+000195900551+U+gold'
    storagegroupname = 'OS-fakehost-gold-I-SG'
    defaultstoragegroupname = 'OS_default_GOLD1_SG'
    re_storagegroup = 'OS-SRP_1-gold-DSS-RE-SG'
    storagevolume_creationclass = 'EMC_StorageVolume'
    policyrule = 'gold'
    poolname = 'gold'
    totalmanagedspace_bits = '1000000000000'
    subscribedcapacity_bits = '500000000000'
    remainingmanagedspace_bits = '500000000000'
    maxsubscriptionpercent = 150
    totalmanagedspace_gbs = 931
    subscribedcapacity_gbs = 465
    remainingmanagedspace_gbs = 465
    fake_host = 'HostX@Backend#gold+1234567891011'
    fake_host_v3 = 'HostX@Backend#Bronze+SRP_1+1234567891011'
    fake_host_2_v3 = 'HostY@Backend#SRP_1+1234567891011'
    fake_host_3_v3 = 'HostX@Backend#Bronze+DSS+SRP_1+1234567891011'
    fake_host_4_v3 = 'HostX@Backend#Silver+None+SRP_1+1234567891011'
    poolInstanceName = {
        'InstanceID': 'SRP_1',
        'CreationClassName': 'Symm_StorageSystem'}

    unit_creationclass = 'CIM_ProtocolControllerForUnit'
    storage_type = 'gold'
    keybindings = {'CreationClassName': u'Symm_StorageVolume',
                   'SystemName': u'SYMMETRIX+000195900551',
                   'DeviceID': u'1',
                   'SystemCreationClassName': u'Symm_StorageSystem'}

    keybindings2 = {'CreationClassName': u'Symm_StorageVolume',
                    'SystemName': u'SYMMETRIX+000195900551',
                    'DeviceID': u'99999',
                    'SystemCreationClassName': u'Symm_StorageSystem'}
    keybindings3 = {'CreationClassName': u'Symm_StorageVolume',
                    'SystemName': u'SYMMETRIX+000195900551',
                    'DeviceID': u'10',
                    'SystemCreationClassName': u'Symm_StorageSystem'}
    re_keybindings = {'CreationClassName': u'Symm_StorageVolume',
                      'SystemName': u'SYMMETRIX+000195900551',
                      'DeviceID': u'1',
                      'SystemCreationClassName': u'Symm_StorageSystem'}
    provider_location = {'classname': 'Symm_StorageVolume',
                         'keybindings': keybindings,
                         'version': '2.5.0'}
    provider_location2 = {'classname': 'Symm_StorageVolume',
                          'keybindings': keybindings2}
    provider_location3 = {'classname': 'Symm_StorageVolume',
                          'keybindings': keybindings3}
    provider_location_multi_pool = {'classname': 'Symm_StorageVolume',
                                    'keybindings': keybindings,
                                    'version': '2.2.0'}

    keybindings_manage = {'CreationClassName': 'Symm_StorageVolume',
                          'SystemName': 'SYMMETRIX+000195900551',
                          'DeviceID': '10',
                          'SystemCreationClassName': 'Symm_StorageSystem'}
    provider_location_manage = {'classname': 'Symm_StorageVolume',
                                'keybindings': keybindings_manage}

    manage_vol = EMC_StorageVolume()
    manage_vol['CreationClassName'] = 'Symm_StorageVolume'
    manage_vol['ElementName'] = 'OS-Test_Manage_vol'
    manage_vol['DeviceID'] = '10'
    manage_vol['SystemName'] = 'SYMMETRIX+000195900551'
    manage_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
    manage_vol.path = manage_vol

    replication_driver_data = re_keybindings
    block_size = 512
    majorVersion = 1
    minorVersion = 2
    revNumber = 3
    block_size = 512

    metaHead_volume = {'DeviceID': 10,
                       'ConsumableBlocks': 1000}
    meta_volume1 = {'DeviceID': 11,
                    'ConsumableBlocks': 200}
    meta_volume2 = {'DeviceID': 12,
                    'ConsumableBlocks': 300}
    properties = {'ConsumableBlocks': '12345',
                  'BlockSize': '512'}

    array = '000197800123'
    array_v3 = '1234567891011'

    test_volume = {'name': 'vol1',
                   'size': 1,
                   'volume_name': 'vol1',
                   'id': '1',
                   'device_id': '1',
                   'provider_auth': None,
                   'project_id': 'project',
                   'display_name': 'vol1',
                   'display_description': 'test volume',
                   'volume_type_id': 'abc',
                   'provider_location': six.text_type(provider_location),
                   'status': 'available',
                   'host': fake_host,
                   'NumberOfBlocks': 100,
                   'BlockSize': block_size
                   }

    test_volume_v2 = {'name': 'vol2',
                      'size': 1,
                      'volume_name': 'vol2',
                      'id': '2',
                      'device_id': '1',
                      'provider_auth': None,
                      'project_id': 'project',
                      'display_name': 'vol1',
                      'display_description': 'test volume',
                      'volume_type_id': 'abc',
                      'provider_location': six.text_type(provider_location),
                      'status': 'available',
                      'host': fake_host,
                      'NumberOfBlocks': 100,
                      'BlockSize': block_size
                      }

    test_volume_v3 = {'name': 'vol3',
                      'size': 1,
                      'volume_name': 'vol3',
                      'id': '3',
                      'device_id': '1',
                      'provider_auth': None,
                      'project_id': 'project',
                      'display_name': 'vol1',
                      'display_description': 'test volume',
                      'volume_type_id': 'abc',
                      'provider_location': six.text_type(provider_location),
                      'status': 'available',
                      'host': fake_host_v3,
                      'NumberOfBlocks': 100,
                      'BlockSize': block_size
                      }

    test_volume_v4 = {'name': 'vol1',
                      'size': 1,
                      'volume_name': 'vol1',
                      'id': '1',
                      'device_id': '1',
                      'provider_auth': None,
                      'project_id': 'project',
                      'display_name': 'vol1',
                      'display_description': 'test volume',
                      'volume_type_id': 'abc',
                      'provider_location': six.text_type(provider_location),
                      'status': 'available',
                      'host': fake_host_3_v3,
                      'NumberOfBlocks': 100,
                      'BlockSize': block_size,
                      'pool_name': 'Bronze+DSS+SRP_1+1234567891011'
                      }

    test_volume_CG = {'name': 'volInCG',
                      'consistencygroup_id': 'abc',
                      'size': 1,
                      'volume_name': 'volInCG',
                      'id': fake_constants.CONSISTENCY_GROUP2_ID,
                      'device_id': '1',
                      'provider_auth': None,
                      'project_id': 'project',
                      'display_name': 'volInCG',
                      'display_description':
                      'test volume in Consistency group',
                      'volume_type_id': 'abc',
                      'provider_location': six.text_type(provider_location),
                      'status': 'available',
                      'host': fake_host
                      }

    test_volume_CG_v3 = consistencygroup.ConsistencyGroup(
        context=None, name='volInCG', consistencygroup_id='abc', size=1,
        volume_name='volInCG', id=fake_constants.CONSISTENCY_GROUP2_ID,
        device_id='1', status='available',
        provider_auth=None, volume_type_id='abc', project_id='project',
        display_name='volInCG',
        display_description='test volume in Consistency group',
        host=fake_host_v3, provider_location=six.text_type(provider_location))

    test_volume_type_QOS = qos_specs.QualityOfServiceSpecs(
        id=fake_constants.QOS_SPEC_ID,
        name='qosName',
        consumer=fields.QoSConsumerValues.BACK_END,
        specs={'maxIOPS': '6000', 'maxMBPS': '6000',
               'DistributionType': 'Always'}
    )

    test_failed_volume = {'name': 'failed_vol',
                          'size': 1,
                          'volume_name': 'failed_vol',
                          'id': '4',
                          'device_id': '1',
                          'provider_auth': None,
                          'project_id': 'project',
                          'display_name': 'failed_vol',
                          'display_description': 'test failed volume',
                          'volume_type_id': 'abc',
                          'host': fake_host}

    failed_delete_vol = {'name': 'failed_delete_vol',
                         'size': '-1',
                         'volume_name': 'failed_delete_vol',
                         'id': '99999',
                         'device_id': '99999',
                         'provider_auth': None,
                         'project_id': 'project',
                         'display_name': 'failed delete vol',
                         'display_description': 'failed delete volume',
                         'volume_type_id': 'abc',
                         'provider_location':
                         six.text_type(provider_location2),
                         'host': fake_host}

    test_source_volume = {'size': 1,
                          'volume_type_id': 'sourceid',
                          'display_name': 'sourceVolume',
                          'name': 'sourceVolume',
                          'device_id': '10',
                          'volume_name': 'vmax-154326',
                          'provider_auth': None,
                          'project_id': 'project',
                          'id': '2',
                          'host': fake_host,
                          'NumberOfBlocks': 100,
                          'BlockSize': block_size,
                          'provider_location':
                          six.text_type(provider_location3),
                          'display_description': 'snapshot source volume'}

    test_source_volume_v3 = {'size': 1,
                             'volume_type_id': 'sourceid',
                             'display_name': 'sourceVolume',
                             'name': 'sourceVolume',
                             'device_id': '10',
                             'volume_name': 'vmax-154326',
                             'provider_auth': None,
                             'project_id': 'project',
                             'id': '2',
                             'host': fake_host_v3,
                             'NumberOfBlocks': 100,
                             'BlockSize': block_size,
                             'provider_location':
                             six.text_type(provider_location3),
                             'display_description': 'snapshot source volume'}

    test_source_volume_1_v3 = {'size': 1,
                               'volume_type_id': 'sourceid',
                               'display_name': 'sourceVolume',
                               'name': 'sourceVolume',
                               'id': 'sourceVolume',
                               'device_id': '10',
                               'volume_name': 'vmax-154326',
                               'provider_auth': None,
                               'project_id': 'project',
                               'host': fake_host_4_v3,
                               'NumberOfBlocks': 100,
                               'BlockSize': block_size,
                               'provider_location':
                                   six.text_type(provider_location),
                               'display_description': 'snapshot source volume'}

    test_volume_re = {'name': 'vol1',
                      'size': 1,
                      'volume_name': 'vol1',
                      'id': '1',
                      'device_id': '1',
                      'provider_auth': None,
                      'project_id': 'project',
                      'display_name': 'vol1',
                      'display_description': 'test volume',
                      'volume_type_id': 'abc',
                      'provider_location': six.text_type(
                          provider_location),
                      'status': 'available',
                      'replication_status': fields.ReplicationStatus.ENABLED,
                      'host': fake_host,
                      'NumberOfBlocks': 100,
                      'BlockSize': block_size,
                      'replication_driver_data': six.text_type(
                          replication_driver_data)}

    test_failed_re_volume = {'name': 'vol1',
                             'size': 1,
                             'volume_name': 'vol1',
                             'id': '1',
                             'device_id': '1',
                             'display_name': 'vol1',
                             'volume_type_id': 'abc',
                             'provider_location': six.text_type(
                                 {'keybindings': 'fake_keybindings'}),
                             'replication_status': (
                                 fields.ReplicationStatus.ENABLED),
                             'replication_driver_data': 'fake_data',
                             'host': fake_host,
                             'NumberOfBlocks': 100,
                             'BlockSize': block_size
                             }

    test_snapshot_re = {'name': 'mySnap',
                        'id': '1',
                        'status': 'available',
                        'host': fake_host,
                        'volume': test_source_volume,
                        'provider_location': six.text_type(provider_location)}

    test_CG = consistencygroup.ConsistencyGroup(
        context=None, name='myCG1', id=fake_constants.UUID1,
        volume_type_id='abc', status=fields.ConsistencyGroupStatus.AVAILABLE)
    source_CG = consistencygroup.ConsistencyGroup(
        context=None, name='myCG1', id='12345abcde',
        volume_type_id='sourceid',
        status=fields.ConsistencyGroupStatus.AVAILABLE)

    deleted_volume = {'id': 'deleted_vol',
                      'provider_location': six.text_type(provider_location)}

    test_snapshot = {'name': 'myCG1',
                     'id': fake_constants.UUID1,
                     'status': 'available',
                     'host': fake_host,
                     'volume': test_source_volume,
                     'provider_location': six.text_type(provider_location)
                     }
    test_snapshot_v3 = {'name': 'myCG1',
                        'id': fake_constants.UUID1,
                        'status': 'available',
                        'host': fake_host_v3,
                        'volume': test_source_volume_v3,
                        'provider_location': six.text_type(provider_location)
                        }
    test_snapshot_1_v3 = {'name': 'mySnap',
                          'id': '1',
                          'status': 'available',
                          'host': fake_host_4_v3,
                          'volume': test_source_volume_1_v3,
                          'provider_location': six.text_type(provider_location)
                          }
    test_CG_snapshot = {'name': 'testSnap',
                        'id': fake_constants.UUID1,
                        'consistencygroup_id': fake_constants.UUID1,
                        'status': 'available',
                        'snapshots': [],
                        'consistencygroup': test_CG
                        }
    location_info = {'location_info': '000195900551#silver#None',
                     'storage_protocol': 'ISCSI'}
    location_info_v3 = {'location_info': '1234567891011#SRP_1#Bronze#DSS',
                        'storage_protocol': 'FC'}
    test_host = {'capabilities': location_info,
                 'host': 'fake_host'}
    test_host_v3 = {'capabilities': location_info_v3,
                    'host': fake_host_2_v3}
    test_host_1_v3 = {'capabilities': location_info_v3,
                      'host': fake_host_4_v3}
    initiatorNames = ["123456789012345", "123456789054321"]
    storagegroups = [{'CreationClassName': storagegroup_creationclass,
                      'ElementName': storagegroupname},
                     {'CreationClassName': storagegroup_creationclass,
                      'ElementName': 'OS-SRP_1-Bronze-DSS-SG'}]
    iqn = u'iqn.1992-04.com.emc:600009700bca30c01e3e012e00000001,t,0x0001'
    iscsi_device_info = {'maskingview': u'OS-host-SRP_1-Diamond-NONE-MV',
                         'ip_and_iqn': [{'ip': u'123.456.7.8',
                                         'iqn': iqn}],
                         'is_multipath': False,
                         'storagesystem': u'SYMMETRIX-+-012345678901',
                         'controller': {'host': '10.00.00.00'},
                         'hostlunid': 3}
    fc_device_info = {'maskingview': u'OS-host-SRP_1-Diamond-NONE-MV',
                      'storagesystem': u'SYMMETRIX-+-012345678901',
                      'controller': {'host': '10.00.00.00'},
                      'hostlunid': 3}
    test_ctxt = {}
    new_type = {'extra_specs': {}}
    diff = {}
    extra_specs = {'storagetype:pool': u'SRP_1',
                   'volume_backend_name': 'V3_BE',
                   'storagetype:workload': u'DSS',
                   'storagetype:slo': u'Bronze',
                   'storagetype:array': u'1234567891011',
                   'MultiPoolSupport': False,
                   'isV3': True,
                   'portgroupname': u'OS-portgroup-PG'}
    extra_specs_no_slo = {'storagetype:pool': 'SRP_1',
                          'volume_backend_name': 'V3_BE',
                          'storagetype:workload': None,
                          'storagetype:slo': None,
                          'storagetype:array': '1234567891011',
                          'isV3': True,
                          'portgroupname': 'OS-portgroup-PG'}

    multi_pool_extra_specs = {'storagetype:pool': u'SRP_1',
                              'volume_backend_name': 'MULTI_POOL_BE',
                              'storagetype:workload': u'DSS',
                              'storagetype:slo': u'Bronze',
                              'storagetype:array': u'1234567891011',
                              'isV3': True,
                              'portgroupname': u'OS-portgroup-PG',
                              'pool_name': u'Bronze+DSS+SRP_1+1234567891011'}

    extra_specs_is_re = {'storagetype:pool': u'SRP_1',
                         'volume_backend_name': 'VMAXReplication',
                         'storagetype:workload': u'DSS',
                         'storagetype:slo': u'Bronze',
                         'storagetype:array': u'1234567891011',
                         'isV3': True,
                         'portgroupname': u'OS-portgroup-PG',
                         'replication_enabled': True,
                         'MultiPoolSupport': False}

    remainingSLOCapacity = '123456789'
    SYNCHRONIZED = 4
    UNSYNCHRONIZED = 3
    multiPoolSupportEnabled = True


class FakeLookupService(object):
    def get_device_mapping_from_network(self, initiator_wwns, target_wwns):
        return VMAXCommonData.device_map


class FakeEcomConnection(object):

    def __init__(self, *args, **kwargs):
        self.data = VMAXCommonData()

    def InvokeMethod(self, MethodName, Service, ElementName=None, InPool=None,
                     ElementType=None, Size=None,
                     SyncType=None, SourceElement=None, TargetElement=None,
                     Operation=None, Synchronization=None,
                     TheElements=None, TheElement=None,
                     LUNames=None, InitiatorPortIDs=None, DeviceAccesses=None,
                     ProtocolControllers=None, ConnectivityCollection=None,
                     MaskingGroup=None, Members=None,
                     HardwareId=None, ElementSource=None, EMCInPools=None,
                     CompositeType=None, EMCNumberOfMembers=None,
                     EMCBindElements=None, Mode=None,
                     InElements=None, TargetPool=None, RequestedState=None,
                     ReplicationGroup=None, ReplicationType=None,
                     ReplicationSettingData=None, GroupName=None, Force=None,
                     RemoveElements=None, RelationshipName=None,
                     SourceGroup=None, TargetGroup=None, Goal=None,
                     Type=None, EMCSRP=None, EMCSLO=None, EMCWorkload=None,
                     EMCCollections=None, InitiatorMaskingGroup=None,
                     DeviceMaskingGroup=None, TargetMaskingGroup=None,
                     ProtocolController=None, StorageID=None, IDType=None,
                     WaitForCopyState=None, Collections=None):

        rc = 0
        myjob = SE_ConcreteJob()
        myjob.classname = 'SE_ConcreteJob'
        myjob['InstanceID'] = '9999'
        myjob['status'] = 'success'
        myjob['type'] = ElementName

        if Size == -1073741824 and (
                MethodName == 'CreateOrModifyCompositeElement'):
            rc = 0
            myjob = SE_ConcreteJob()
            myjob.classname = 'SE_ConcreteJob'
            myjob['InstanceID'] = '99999'
            myjob['status'] = 'success'
            myjob['type'] = 'failed_delete_vol'

        if ElementName == 'failed_vol' and (
                MethodName == 'CreateOrModifyElementFromStoragePool'):
            rc = 10
            myjob['status'] = 'failure'

        elif TheElements and TheElements[0]['DeviceID'] == '99999' and (
                MethodName == 'ReturnElementsToStoragePool'):
            rc = 10
            myjob['status'] = 'failure'
        elif HardwareId:
            rc = 0
            targetendpoints = {}
            endpoints = []
            endpoint = {}
            endpoint['Name'] = (VMAXCommonData.end_point_map[
                VMAXCommonData.connector['wwpns'][0]])
            endpoints.append(endpoint)
            endpoint2 = {}
            endpoint2['Name'] = (VMAXCommonData.end_point_map[
                VMAXCommonData.connector['wwpns'][1]])
            endpoints.append(endpoint2)
            targetendpoints['TargetEndpoints'] = endpoints
            return rc, targetendpoints
        elif ReplicationType and (
                MethodName == 'GetDefaultReplicationSettingData'):
            rc = 0
            rsd = SE_ReplicationSettingData()
            rsd['DefaultInstance'] = SE_ReplicationSettingData()
            return rc, rsd
        if MethodName == 'CreateStorageHardwareID':
            ret = {}
            rc = 0
            ret['HardwareID'] = self.data.iscsi_initiator
            return rc, ret
        if MethodName == 'GetSupportedSizeRange':
            ret = {}
            rc = 0
            ret['EMCInformationSource'] = 3
            ret['EMCRemainingSLOCapacity'] = self.data.remainingSLOCapacity
            return rc, ret
        elif MethodName == 'GetCompositeElements':
            ret = {}
            rc = 0
            ret['OutElements'] = [self.data.metaHead_volume,
                                  self.data.meta_volume1,
                                  self.data.meta_volume2]
            return rc, ret
        if (MethodName == 'CreateGroup' and
                GroupName == self.data.initiatorgroup_name):
            rc = 0
            job = {}
            job['MaskingGroup'] = GroupName
            return rc, job
        if MethodName == 'CreateGroup' and GroupName == 'IG_unsuccessful':
            rc = 10
            job = {}
            job['status'] = 'failure'
            return rc, job

        job = {'Job': myjob}
        return rc, job

    def EnumerateInstanceNames(self, name):
        result = None
        if name == 'EMC_StorageConfigurationService':
            result = self._enum_stconfsvcs()
        elif name == 'EMC_ControllerConfigurationService':
            result = self._enum_ctrlconfsvcs()
        elif name == 'Symm_ElementCompositionService':
            result = self._enum_elemcompsvcs()
        elif name == 'Symm_StorageRelocationService':
            result = self._enum_storrelocsvcs()
        elif name == 'EMC_ReplicationService':
            result = self._enum_replicsvcs()
        elif name == 'EMC_VirtualProvisioningPool':
            result = self._enum_pools()
        elif name == 'EMC_StorageVolume':
            result = self._enum_storagevolumes()
        elif name == 'Symm_StorageVolume':
            result = self._enum_storagevolumes()
        elif name == 'CIM_StorageVolume':
            result = self._enum_storagevolumes()
        elif name == 'CIM_ProtocolControllerForUnit':
            result = self._enum_unitnames()
        elif name == 'EMC_LunMaskingSCSIProtocolController':
            result = self._enum_lunmaskctrls()
        elif name == 'EMC_StorageProcessorSystem':
            result = self._enum_processors()
        elif name == 'EMC_StorageHardwareIDManagementService':
            result = self._enum_hdwidmgmts()
        elif name == 'SE_StorageHardwareID':
            result = self._enum_storhdwids()
        elif name == 'EMC_StorageSystem':
            result = self._enum_storagesystems()
        elif name == 'Symm_TierPolicyRule':
            result = self._enum_policyrules()
        elif name == 'CIM_ReplicationServiceCapabilities':
            result = self._enum_repservcpbls()
        elif name == 'SE_StorageSynchronized_SV_SV':
            result = self._enum_storageSyncSvSv()
        elif name == 'Symm_SRPStoragePool':
            result = self._enum_srpstoragepool()
        elif name == 'Symm_ArrayChassis':
            result = self._enum_arraychassis()
        else:
            result = self._default_enum()
        return result

    def EnumerateInstances(self, name):
        result = None
        if name == 'EMC_VirtualProvisioningPool':
            result = self._enum_pool_details()
        elif name == 'SE_StorageHardwareID':
            result = self._enum_storhdwids()
        elif name == 'SE_ManagementServerSoftwareIdentity':
            result = self._enum_sw_identity()
        else:
            result = self._default_enum()
        return result

    def GetInstance(self, objectpath, LocalOnly=False):
        try:
            name = objectpath['CreationClassName']
        except KeyError:
            name = objectpath.classname
        result = None
        if name == 'Symm_StorageVolume':
            result = self._getinstance_storagevolume(objectpath)
        elif name == 'CIM_ProtocolControllerForUnit':
            result = self._getinstance_unit(objectpath)
        elif name == 'SE_ConcreteJob':
            result = self._getinstance_job(objectpath)
        elif name == 'SE_StorageSynchronized_SV_SV':
            result = self._getinstance_syncsvsv(objectpath)
        elif name == 'Symm_TierPolicyServiceCapabilities':
            result = self._getinstance_policycapabilities(objectpath)
        elif name == 'CIM_TierPolicyServiceCapabilities':
            result = self._getinstance_policycapabilities(objectpath)
        elif name == 'SE_InitiatorMaskingGroup':
            result = self._getinstance_initiatormaskinggroup(objectpath)
        elif name == 'CIM_InitiatorMaskingGroup':
            result = self._getinstance_initiatormaskinggroup(objectpath)
        elif name == 'SE_StorageHardwareID':
            result = self._getinstance_storagehardwareid(objectpath)
        elif name == 'CIM_ReplicationGroup':
            result = self._getinstance_replicationgroup(objectpath)
        elif name == 'Symm_SRPStoragePool':
            result = self._getinstance_srpstoragepool(objectpath)
        elif name == 'CIM_TargetMaskingGroup':
            result = self._getinstance_targetmaskinggroup(objectpath)
        elif name == 'CIM_DeviceMaskingGroup':
            result = self._getinstance_devicemaskinggroup(objectpath)
        elif name == 'EMC_StorageHardwareID':
            result = self._getinstance_storagehardwareid(objectpath)
        elif name == 'Symm_VirtualProvisioningPool':
            result = self._getinstance_pool(objectpath)
        elif name == 'Symm_ReplicationServiceCapabilities':
            result = self._getinstance_replicationServCapabilities(objectpath)
        else:
            result = self._default_getinstance(objectpath)

        return result

    def ModifyInstance(self, objectpath, PropertyList=None):
            pass

    def DeleteInstance(self, objectpath):
        pass

    def Associators(self, objectpath, ResultClass='EMC_StorageHardwareID'):
        result = None
        if '_StorageHardwareID' in ResultClass:
            result = self._assoc_hdwid()
        elif ResultClass == 'EMC_iSCSIProtocolEndpoint':
            result = self._assoc_endpoint()
        elif ResultClass == 'EMC_StorageVolume':
            result = self._assoc_storagevolume(objectpath)
        elif ResultClass == 'Symm_LunMaskingView':
            result = self._assoc_maskingview()
        elif ResultClass == 'CIM_DeviceMaskingGroup':
            result = self._assoc_storagegroup()
        elif ResultClass == 'CIM_StorageExtent':
            result = self._assoc_storageextent()
        elif ResultClass == 'EMC_LunMaskingSCSIProtocolController':
            result = self._assoc_lunmaskctrls()
        elif ResultClass == 'CIM_TargetMaskingGroup':
            result = self._assoc_portgroup()
        elif ResultClass == 'CIM_ConnectivityCollection':
            result = self._assoc_rdfgroup()
        else:
            result = self._default_assoc(objectpath)
        return result

    def AssociatorNames(self, objectpath,
                        ResultClass='default', AssocClass='default'):
        result = None
        if objectpath == 'point_to_storage_instance_names':
            result = ['FirstStorageTierInstanceNames']

        if ResultClass != 'default':
            result = self.ResultClassHelper(ResultClass, objectpath)

        if result is None and AssocClass != 'default':
            result = self.AssocClassHelper(AssocClass, objectpath)
        if result is None:
            result = self._default_assocnames(objectpath)
        return result

    def AssocClassHelper(self, AssocClass, objectpath):
        if AssocClass == 'CIM_HostedService':
            result = self._assocnames_hostedservice()
        elif AssocClass == 'CIM_AssociatedTierPolicy':
            result = self._assocnames_assoctierpolicy()
        elif AssocClass == 'CIM_OrderedMemberOfCollection':
            result = self._enum_storagevolumes()
        elif AssocClass == 'CIM_BindsTo':
            result = self._assocnames_bindsto()
        elif AssocClass == 'CIM_MemberOfCollection':
            result = self._assocnames_memberofcollection()
        else:
            result = None
        return result

    def ResultClassHelper(self, ResultClass, objectpath):
        if ResultClass == 'EMC_LunMaskingSCSIProtocolController':
            result = self._assocnames_lunmaskctrl()
        elif ResultClass == 'CIM_TierPolicyServiceCapabilities':
            result = self._assocnames_policyCapabilities()
        elif ResultClass == 'Symm_TierPolicyRule':
            result = self._assocnames_policyrule()
        elif ResultClass == 'CIM_StoragePool':
            result = self._assocnames_storagepool()
        elif ResultClass == 'EMC_VirtualProvisioningPool':
            result = self._assocnames_storagepool()
        elif ResultClass == 'CIM_DeviceMaskingGroup':
            result = self._assocnames_storagegroup()
        elif ResultClass == 'EMC_StorageVolume':
            result = self._enum_storagevolumes()
        elif ResultClass == 'Symm_StorageVolume':
            result = self._enum_storagevolumes()
        elif ResultClass == 'SE_InitiatorMaskingGroup':
            result = self._enum_initiatorMaskingGroup()
        elif ResultClass == 'CIM_InitiatorMaskingGroup':
            result = self._enum_initiatorMaskingGroup()
        elif ResultClass == 'CIM_StorageExtent':
            result = self._enum_storage_extent()
        elif ResultClass == 'SE_StorageHardwareID':
            result = self._enum_storhdwids()
        elif ResultClass == 'CIM_ReplicationServiceCapabilities':
            result = self._enum_repservcpbls()
        elif ResultClass == 'CIM_ReplicationGroup':
            result = self._enum_repgroups()
        elif ResultClass == 'Symm_FCSCSIProtocolEndpoint':
            result = self._enum_fcscsiendpoint()
        elif ResultClass == 'EMC_FCSCSIProtocolEndpoint':
            result = self._enum_fcscsiendpoint()
        elif ResultClass == 'Symm_SRPStoragePool':
            result = self._enum_srpstoragepool()
        elif ResultClass == 'Symm_StoragePoolCapabilities':
            result = self._enum_storagepoolcapabilities()
        elif ResultClass == 'CIM_storageSetting':
            result = self._enum_storagesettings()
        elif ResultClass == 'CIM_TargetMaskingGroup':
            result = self._assocnames_portgroup()
        elif ResultClass == 'CIM_InitiatorMaskingGroup':
            result = self._enum_initMaskingGroup()
        elif ResultClass == 'Symm_LunMaskingView':
            result = self._enum_maskingView()
        elif ResultClass == 'EMC_Meta':
            result = self._enum_metavolume()
        elif ResultClass == 'EMC_FrontEndSCSIProtocolController':
            result = self._enum_maskingView()
        elif ResultClass == 'CIM_TierPolicyRule':
            result = self._assocnames_tierpolicy(objectpath)
        else:
            result = None
        return result

    def ReferenceNames(self, objectpath,
                       ResultClass='CIM_ProtocolControllerForUnit'):
        result = None
        if ResultClass == 'CIM_ProtocolControllerForUnit':
            result = self._ref_unitnames2()
        elif ResultClass == 'SE_StorageSynchronized_SV_SV':
            result = self._enum_storageSyncSvSv()
        else:
            result = self._default_ref(objectpath)
        return result

    def _ref_unitnames(self):
        unitnames = []
        unitname = {}

        dependent = {}
        dependent['CreationClassName'] = self.data.vol_creationclass
        dependent['DeviceID'] = self.data.test_volume['id']
        dependent['ElementName'] = self.data.test_volume['name']
        dependent['SystemName'] = self.data.storage_system

        antecedent = {}
        antecedent['CreationClassName'] = self.data.lunmask_creationclass
        antecedent['DeviceID'] = self.data.lunmaskctrl_id
        antecedent['SystemName'] = self.data.storage_system

        unitname['Dependent'] = dependent
        unitname['Antecedent'] = antecedent
        unitname['CreationClassName'] = self.data.unit_creationclass
        unitnames.append(unitname)

        return unitnames

    def mv_entry(self, mvname):
        unitname = {}

        dependent = {}
        dependent['CreationClassName'] = self.data.vol_creationclass
        dependent['DeviceID'] = self.data.test_volume['id']
        dependent['ElementName'] = self.data.test_volume['name']
        dependent['SystemName'] = self.data.storage_system

        antecedent = SYMM_LunMasking()
        antecedent['CreationClassName'] = self.data.lunmask_creationclass2
        antecedent['SystemName'] = self.data.storage_system
        antecedent['ElementName'] = mvname

        classcimproperty = Fake_CIMProperty()
        elementName = (
            classcimproperty.fake_getElementNameCIMProperty(mvname))
        properties = {u'ElementName': elementName}
        antecedent.properties = properties

        unitname['Dependent'] = dependent
        unitname['Antecedent'] = antecedent
        unitname['CreationClassName'] = self.data.unit_creationclass
        return unitname

    def _ref_unitnames2(self):
        unitnames = []
        unitname = self.mv_entry('OS-myhost-MV')
        unitnames.append(unitname)

        # Second masking
        unitname2 = self.mv_entry('OS-fakehost-MV')
        unitnames.append(unitname2)

        # third masking
        amended = 'OS-rslong493156848e71b072a17c1c4625e45f75-MV'
        unitname3 = self.mv_entry(amended)
        unitnames.append(unitname3)
        return unitnames

    def _default_ref(self, objectpath):
        return objectpath

    def _assoc_hdwid(self):
        assocs = []
        assoc = EMC_StorageHardwareID()
        assoc['StorageID'] = self.data.connector['initiator']
        assoc['SystemName'] = self.data.storage_system
        assoc['CreationClassName'] = 'EMC_StorageHardwareID'
        assoc.path = assoc
        assocs.append(assoc)
        for wwpn in self.data.connector['wwpns']:
            assoc2 = EMC_StorageHardwareID()
            assoc2['StorageID'] = wwpn
            assoc2['SystemName'] = self.data.storage_system
            assoc2['CreationClassName'] = 'EMC_StorageHardwareID'
            assoc2.path = assoc2
            assocs.append(assoc2)
        assocs.append(assoc)
        return assocs

    def _assoc_endpoint(self):
        assocs = []
        assoc = {}
        assoc['Name'] = 'iqn.1992-04.com.emc: 50000973f006dd80'
        assoc['SystemName'] = self.data.storage_system
        assocs.append(assoc)
        return assocs

    def _assoc_storagegroup(self):
        assocs = []
        assoc1 = CIM_DeviceMaskingGroup()
        assoc1['ElementName'] = self.data.storagegroupname
        assoc1['SystemName'] = self.data.storage_system
        assoc1['CreationClassName'] = 'CIM_DeviceMaskingGroup'
        assoc1.path = assoc1
        assocs.append(assoc1)
        assoc2 = CIM_DeviceMaskingGroup()
        assoc2['ElementName'] = self.data.defaultstoragegroupname
        assoc2['SystemName'] = self.data.storage_system
        assoc2['CreationClassName'] = 'CIM_DeviceMaskingGroup'
        assoc2.path = assoc2
        assocs.append(assoc2)
        return assocs

    def _assoc_portgroup(self):
        assocs = []
        assoc = CIM_TargetMaskingGroup()
        assoc['ElementName'] = self.data.port_group
        assoc['SystemName'] = self.data.storage_system
        assoc['CreationClassName'] = 'CIM_TargetMaskingGroup'
        assoc.path = assoc
        assocs.append(assoc)
        return assocs

    def _assoc_lunmaskctrls(self):
        ctrls = []
        ctrl = EMC_LunMaskingSCSIProtocolController()
        ctrl['CreationClassName'] = self.data.lunmask_creationclass
        ctrl['DeviceID'] = self.data.lunmaskctrl_id
        ctrl['SystemName'] = self.data.storage_system
        ctrl['ElementName'] = self.data.lunmaskctrl_name
        ctrl.path = ctrl
        ctrls.append(ctrl)
        return ctrls

    def _assoc_maskingview(self):
        assocs = []
        assoc = SYMM_LunMasking()
        assoc['Name'] = 'myMaskingView'
        assoc['SystemName'] = self.data.storage_system
        assoc['CreationClassName'] = 'Symm_LunMaskingView'
        assoc['DeviceID'] = '1234'
        assoc['SystemCreationClassName'] = '1234'
        assoc['ElementName'] = 'OS-fakehost-gold-I-MV'
        assoc.classname = assoc['CreationClassName']
        assoc.path = assoc
        assocs.append(assoc)
        return assocs

    # Added test for EMC_StorageVolume associators
    def _assoc_storagevolume(self, objectpath):
        assocs = []
        if 'type' not in objectpath:
            vol = self.data.test_volume
        elif objectpath['type'] == 'failed_delete_vol':
            vol = self.data.failed_delete_vol
        elif objectpath['type'] == 'vol1':
            vol = self.data.test_volume
        elif objectpath['type'] == 'volInCG':
            vol = self.data.test_volume_CG
        elif objectpath['type'] == 'appendVolume':
            vol = self.data.test_volume
        elif objectpath['type'] == 'failed_vol':
            vol = self.data.test_failed_volume
        else:
            vol = self.data.test_volume

        vol['DeviceID'] = vol['device_id']
        assoc = self._getinstance_storagevolume(vol)

        assocs.append(assoc)
        return assocs

    def _assoc_storageextent(self):
        assocs = []
        assoc = CIM_StorageExtent()
        assoc['Name'] = 'myStorageExtent'
        assoc['SystemName'] = self.data.storage_system
        assoc['CreationClassName'] = 'CIM_StorageExtent'
        assoc.classname = assoc['CreationClassName']
        assoc.path = assoc
        classcimproperty = Fake_CIMProperty()
        isConcatenatedcimproperty = (
            classcimproperty.fake_getIsCompositeCIMProperty())
        properties = {u'IsConcatenated': isConcatenatedcimproperty}
        assoc.properties = properties
        assocs.append(assoc)
        return assocs

    def _assoc_rdfgroup(self):
        assocs = []
        assoc = CIM_ConnectivityCollection()
        assoc['ElementName'] = self.data.rdf_group
        assoc.path = self.data.srdf_group_instance
        assocs.append(assoc)
        return assocs

    def _default_assoc(self, objectpath):
        return objectpath

    def _assocnames_lunmaskctrl(self):
        return self._enum_lunmaskctrls()

    def _assocnames_hostedservice(self):
        return self._enum_hostedservice()

    def _assocnames_policyCapabilities(self):
        return self._enum_policycapabilities()

    def _assocnames_policyrule(self):
        return self._enum_policyrules()

    def _assocnames_assoctierpolicy(self):
        return self._enum_assoctierpolicy()

    def _assocnames_storagepool(self):
        return self._enum_storagepool()

    def _assocnames_storagegroup(self):
        return self._enum_storagegroup()

    def _assocnames_storagevolume(self):
        return self._enum_storagevolume()

    def _assocnames_portgroup(self):
        return self._enum_portgroup()

    def _assocnames_memberofcollection(self):
        return self._enum_hostedservice()

    def _assocnames_bindsto(self):
        return self._enum_ipprotocolendpoint()

    def _default_assocnames(self, objectpath):
        return objectpath

    def _getinstance_storagevolume(self, objectpath):
        foundinstance = None
        instance = EMC_StorageVolume()
        vols = self._enum_storagevolumes()

        for vol in vols:
            if vol['DeviceID'] == objectpath['DeviceID']:
                instance = vol
                break
        if not instance:
            foundinstance = None
        else:
            foundinstance = instance

        return foundinstance

    def _getinstance_lunmask(self):
        lunmask = {}
        lunmask['CreationClassName'] = self.data.lunmask_creationclass
        lunmask['DeviceID'] = self.data.lunmaskctrl_id
        lunmask['SystemName'] = self.data.storage_system
        return lunmask

    def _getinstance_initiatormaskinggroup(self, objectpath):

        initiatorgroup = SE_InitiatorMaskingGroup()
        initiatorgroup['CreationClassName'] = (
            self.data.initiatorgroup_creationclass)
        initiatorgroup['DeviceID'] = self.data.initiatorgroup_id
        initiatorgroup['SystemName'] = self.data.storage_system
        initiatorgroup['ElementName'] = self.data.initiatorgroup_name
        initiatorgroup.path = initiatorgroup
        return initiatorgroup

    def _getinstance_storagehardwareid(self, objectpath):
        hardwareid = SE_StorageHardwareID()
        hardwareid['CreationClassName'] = self.data.hardwareid_creationclass
        hardwareid['SystemName'] = self.data.storage_system
        hardwareid['StorageID'] = self.data.connector['wwpns'][0]
        hardwareid.path = hardwareid
        return hardwareid

    def _getinstance_pool(self, objectpath):
        pool = {}
        pool['CreationClassName'] = 'Symm_VirtualProvisioningPool'
        pool['ElementName'] = self.data.poolname
        pool['SystemName'] = self.data.storage_system
        pool['TotalManagedSpace'] = self.data.totalmanagedspace_bits
        pool['EMCSubscribedCapacity'] = self.data.subscribedcapacity_bits
        pool['RemainingManagedSpace'] = self.data.remainingmanagedspace_bits
        pool['EMCMaxSubscriptionPercent'] = self.data.maxsubscriptionpercent
        return pool

    def _getinstance_replicationgroup(self, objectpath):
        replicationgroup = {}
        replicationgroup['CreationClassName'] = (
            self.data.replicationgroup_creationclass)
        replicationgroup['ElementName'] = fake_constants.UUID1
        return replicationgroup

    def _getinstance_srpstoragepool(self, objectpath):
        srpstoragepool = SYMM_SrpStoragePool()
        srpstoragepool['CreationClassName'] = (
            self.data.srpstoragepool_creationclass)
        srpstoragepool['ElementName'] = 'SRP_1'

        classcimproperty = Fake_CIMProperty()
        totalManagedSpace = (
            classcimproperty.fake_getTotalManagedSpaceCIMProperty())
        remainingManagedSpace = (
            classcimproperty.fake_getRemainingManagedSpaceCIMProperty())
        properties = {u'TotalManagedSpace': totalManagedSpace,
                      u'RemainingManagedSpace': remainingManagedSpace}
        srpstoragepool.properties = properties
        return srpstoragepool

    def _getinstance_targetmaskinggroup(self, objectpath):
        targetmaskinggroup = CIM_TargetMaskingGroup()
        targetmaskinggroup['CreationClassName'] = 'CIM_TargetMaskingGroup'
        targetmaskinggroup['ElementName'] = self.data.port_group
        targetmaskinggroup.path = targetmaskinggroup
        return targetmaskinggroup

    def _getinstance_devicemaskinggroup(self, objectpath):
        targetmaskinggroup = {}
        if 'CreationClassName' in objectpath:
            targetmaskinggroup['CreationClassName'] = (
                objectpath['CreationClassName'])
        else:
            targetmaskinggroup['CreationClassName'] = (
                'CIM_DeviceMaskingGroup')
        if 'ElementName' in objectpath:
            targetmaskinggroup['ElementName'] = objectpath['ElementName']
        else:
            targetmaskinggroup['ElementName'] = (
                self.data.storagegroupname)
        if 'EMCMaximumIO' in objectpath:
            targetmaskinggroup['EMCMaximumIO'] = objectpath['EMCMaximumIO']
        if 'EMCMaximumBandwidth' in objectpath:
            targetmaskinggroup['EMCMaximumBandwidth'] = (
                objectpath['EMCMaximumBandwidth'])
        if 'EMCMaxIODynamicDistributionType' in objectpath:
            targetmaskinggroup['EMCMaxIODynamicDistributionType'] = (
                objectpath['EMCMaxIODynamicDistributionType'])
        return targetmaskinggroup

    def _getinstance_unit(self, objectpath):
        unit = {}

        dependent = {}
        dependent['CreationClassName'] = self.data.vol_creationclass
        dependent['DeviceID'] = self.data.test_volume['id']
        dependent['ElementName'] = self.data.test_volume['name']
        dependent['SystemName'] = self.data.storage_system

        antecedent = {}
        antecedent['CreationClassName'] = self.data.lunmask_creationclass
        antecedent['DeviceID'] = self.data.lunmaskctrl_id
        antecedent['SystemName'] = self.data.storage_system

        unit['Dependent'] = dependent
        unit['Antecedent'] = antecedent
        unit['CreationClassName'] = self.data.unit_creationclass
        unit['DeviceNumber'] = '1'

        return unit

    def _getinstance_job(self, jobpath):
        jobinstance = {}
        jobinstance['InstanceID'] = '9999'
        if jobpath['status'] == 'failure':
            jobinstance['JobState'] = 10
            jobinstance['ErrorCode'] = 99
            jobinstance['ErrorDescription'] = 'Failure'
        else:
            jobinstance['JobState'] = 7
            jobinstance['ErrorCode'] = 0
            jobinstance['ErrorDescription'] = None
            jobinstance['OperationalStatus'] = (2, 17)
        return jobinstance

    def _getinstance_policycapabilities(self, policycapabilitypath):
        instance = Fake_CIM_TierPolicyServiceCapabilities()
        fakeinstance = instance.fake_getpolicyinstance()
        return fakeinstance

    def _getinstance_syncsvsv(self, objectpath):
        svInstance = {}
        svInstance['SyncedElement'] = 'SyncedElement'
        svInstance['SystemElement'] = 'SystemElement'
        svInstance['PercentSynced'] = 100
        if 'PercentSynced' in objectpath and objectpath['PercentSynced'] < 100:
            svInstance['PercentSynced'] = 50
        svInstance['CopyState'] = self.data.SYNCHRONIZED
        if 'CopyState' in objectpath and (
                objectpath['CopyState'] != self.data.SYNCHRONIZED):
            svInstance['CopyState'] = self.data.UNSYNCHRONIZED
        return svInstance

    def _getinstance_replicationServCapabilities(self, objectpath):
        repServCpblInstance = SYMM_SrpStoragePool()
        classcimproperty = Fake_CIMProperty()
        repTypesCimproperty = (
            classcimproperty.fake_getSupportedReplicationTypes())
        properties = {u'SupportedReplicationTypes': repTypesCimproperty}
        repServCpblInstance.properties = properties
        return repServCpblInstance

    def _getinstance_ipprotocolendpoint(self, objectpath):
        return self._enum_ipprotocolendpoint()[0]

    def _getinstance_lunmaskingview(self, objectpath):
        return self._enum_maskingView()[0]

    def _default_getinstance(self, objectpath):
        return objectpath

    def _enum_stconfsvcs(self):
        conf_services = []
        conf_service1 = {}
        conf_service1['SystemName'] = self.data.storage_system
        conf_service1['CreationClassName'] = (
            self.data.stconf_service_creationclass)
        conf_services.append(conf_service1)
        conf_service2 = {}
        conf_service2['SystemName'] = self.data.storage_system_v3
        conf_service2['CreationClassName'] = (
            self.data.stconf_service_creationclass)
        conf_services.append(conf_service2)
        return conf_services

    def _enum_ctrlconfsvcs(self):
        conf_services = []
        conf_service = {}
        conf_service['SystemName'] = self.data.storage_system
        conf_service['CreationClassName'] = (
            self.data.ctrlconf_service_creationclass)
        conf_services.append(conf_service)
        conf_service1 = {}
        conf_service1['SystemName'] = self.data.storage_system_v3
        conf_service1['CreationClassName'] = (
            self.data.ctrlconf_service_creationclass)
        conf_services.append(conf_service1)
        return conf_services

    def _enum_elemcompsvcs(self):
        comp_services = []
        comp_service = {}
        comp_service['SystemName'] = self.data.storage_system
        comp_service['CreationClassName'] = (
            self.data.elementcomp_service_creationclass)
        comp_services.append(comp_service)
        return comp_services

    def _enum_storrelocsvcs(self):
        reloc_services = []
        reloc_service = {}
        reloc_service['SystemName'] = self.data.storage_system
        reloc_service['CreationClassName'] = (
            self.data.storreloc_service_creationclass)
        reloc_services.append(reloc_service)
        return reloc_services

    def _enum_replicsvcs(self):
        replic_services = []
        replic_service = {}
        replic_service['SystemName'] = self.data.storage_system
        replic_service['CreationClassName'] = (
            self.data.replication_service_creationclass)
        replic_services.append(replic_service)
        replic_service2 = {}
        replic_service2['SystemName'] = self.data.storage_system_v3
        replic_service2['CreationClassName'] = (
            self.data.replication_service_creationclass)
        replic_services.append(replic_service2)
        return replic_services

    def _enum_pools(self):
        pools = []
        pool = {}
        pool['InstanceID'] = (
            self.data.storage_system + '+U+' + self.data.storage_type)
        pool['CreationClassName'] = 'Symm_VirtualProvisioningPool'
        pool['ElementName'] = 'gold'
        pools.append(pool)
        return pools

    def _enum_pool_details(self):
        pools = []
        pool = {}
        pool['InstanceID'] = (
            self.data.storage_system + '+U+' + self.data.storage_type)
        pool['CreationClassName'] = 'Symm_VirtualProvisioningPool'
        pool['TotalManagedSpace'] = 12345678
        pool['RemainingManagedSpace'] = 123456
        pools.append(pool)
        return pools

    def _enum_storagevolumes(self):
        vols = []

        vol = EMC_StorageVolume()
        vol['Name'] = self.data.test_volume['name']
        vol['CreationClassName'] = 'Symm_StorageVolume'
        vol['ElementName'] = self.data.test_volume['id']
        vol['DeviceID'] = self.data.test_volume['device_id']
        vol['Id'] = self.data.test_volume['id']
        vol['SystemName'] = self.data.storage_system
        vol['NumberOfBlocks'] = self.data.test_volume['NumberOfBlocks']
        vol['BlockSize'] = self.data.test_volume['BlockSize']

        # Added vol to vol.path
        vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        vol.path = vol
        vol.path.classname = vol['CreationClassName']

        classcimproperty = Fake_CIMProperty()
        blocksizecimproperty = classcimproperty.fake_getBlockSizeCIMProperty()
        consumableBlockscimproperty = (
            classcimproperty.fake_getConsumableBlocksCIMProperty())
        isCompositecimproperty = (
            classcimproperty.fake_getIsCompositeCIMProperty())
        properties = {u'ConsumableBlocks': blocksizecimproperty,
                      u'BlockSize': consumableBlockscimproperty,
                      u'IsComposite': isCompositecimproperty}
        vol.properties = properties

        name = {}
        name['classname'] = 'Symm_StorageVolume'
        keys = {}
        keys['CreationClassName'] = 'Symm_StorageVolume'
        keys['SystemName'] = self.data.storage_system
        keys['DeviceID'] = vol['DeviceID']
        keys['SystemCreationClassName'] = 'Symm_StorageSystem'
        name['keybindings'] = keys

        vol['provider_location'] = str(name)

        vols.append(vol)

        failed_delete_vol = EMC_StorageVolume()
        failed_delete_vol['name'] = 'failed_delete_vol'
        failed_delete_vol['CreationClassName'] = 'Symm_StorageVolume'
        failed_delete_vol['ElementName'] = self.data.failed_delete_vol['id']
        failed_delete_vol['DeviceID'] = '99999'
        failed_delete_vol['SystemName'] = self.data.storage_system
        # Added vol to vol.path
        failed_delete_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        failed_delete_vol.path = failed_delete_vol
        failed_delete_vol.path.classname = (
            failed_delete_vol['CreationClassName'])
        vols.append(failed_delete_vol)

        failed_vol = EMC_StorageVolume()
        failed_vol['name'] = 'failed__vol'
        failed_vol['CreationClassName'] = 'Symm_StorageVolume'
        failed_vol['ElementName'] = 'failed_vol'
        failed_vol['DeviceID'] = '4'
        failed_vol['SystemName'] = self.data.storage_system
        # Added vol to vol.path
        failed_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        failed_vol.path = failed_vol
        failed_vol.path.classname = failed_vol['CreationClassName']

        name_failed = {}
        name_failed['classname'] = 'Symm_StorageVolume'
        keys_failed = {}
        keys_failed['CreationClassName'] = 'Symm_StorageVolume'
        keys_failed['SystemName'] = self.data.storage_system
        keys_failed['DeviceID'] = failed_vol['DeviceID']
        keys_failed['SystemCreationClassName'] = 'Symm_StorageSystem'
        name_failed['keybindings'] = keys_failed
        failed_vol['provider_location'] = str(name_failed)

        vols.append(failed_vol)

        volumeHead = EMC_StorageVolume()
        volumeHead.classname = 'Symm_StorageVolume'
        blockSize = self.data.block_size
        volumeHead['ConsumableBlocks'] = (
            self.data.metaHead_volume['ConsumableBlocks'])
        volumeHead['BlockSize'] = blockSize
        volumeHead['DeviceID'] = self.data.metaHead_volume['DeviceID']
        vols.append(volumeHead)

        metaMember1 = EMC_StorageVolume()
        metaMember1.classname = 'Symm_StorageVolume'
        metaMember1['ConsumableBlocks'] = (
            self.data.meta_volume1['ConsumableBlocks'])
        metaMember1['BlockSize'] = blockSize
        metaMember1['DeviceID'] = self.data.meta_volume1['DeviceID']
        vols.append(metaMember1)

        metaMember2 = EMC_StorageVolume()
        metaMember2.classname = 'Symm_StorageVolume'
        metaMember2['ConsumableBlocks'] = (
            self.data.meta_volume2['ConsumableBlocks'])
        metaMember2['BlockSize'] = blockSize
        metaMember2['DeviceID'] = self.data.meta_volume2['DeviceID']
        vols.append(metaMember2)

        source_volume = EMC_StorageVolume()
        source_volume['name'] = self.data.test_source_volume['name']
        source_volume['CreationClassName'] = 'Symm_StorageVolume'
        source_volume['ElementName'] = self.data.test_source_volume['id']
        source_volume['DeviceID'] = self.data.test_source_volume['device_id']
        source_volume['Id'] = self.data.test_source_volume['id']
        source_volume['SystemName'] = self.data.storage_system
        source_volume['NumberOfBlocks'] = (
            self.data.test_source_volume['NumberOfBlocks'])
        source_volume['BlockSize'] = self.data.test_source_volume['BlockSize']
        source_volume['SystemCreationClassName'] = 'Symm_StorageSystem'
        source_volume.path = source_volume
        source_volume.path.classname = source_volume['CreationClassName']
        source_volume.properties = properties
        vols.append(source_volume)

        return vols

    def _enum_initiatorMaskingGroup(self):
        initatorgroups = []
        initatorgroup = {}
        initatorgroup['CreationClassName'] = (
            self.data.initiatorgroup_creationclass)
        initatorgroup['DeviceID'] = self.data.initiatorgroup_id
        initatorgroup['SystemName'] = self.data.storage_system
        initatorgroup['ElementName'] = self.data.initiatorgroup_name
        initatorgroups.append(initatorgroup)
        return initatorgroups

    def _enum_storage_extent(self):
        storageExtents = []
        storageExtent = CIM_StorageExtent()
        storageExtent['CreationClassName'] = (
            self.data.storageextent_creationclass)

        classcimproperty = Fake_CIMProperty()
        isConcatenatedcimproperty = (
            classcimproperty.fake_getIsConcatenatedCIMProperty())
        properties = {u'IsConcatenated': isConcatenatedcimproperty}
        storageExtent.properties = properties

        storageExtents.append(storageExtent)
        return storageExtents

    def _enum_lunmaskctrls(self):
        ctrls = []
        ctrl = {}
        ctrl['CreationClassName'] = self.data.lunmask_creationclass
        ctrl['DeviceID'] = self.data.lunmaskctrl_id
        ctrl['SystemName'] = self.data.storage_system
        ctrl['ElementName'] = self.data.lunmaskctrl_name
        ctrls.append(ctrl)
        return ctrls

    def _enum_hostedservice(self):
        hostedservices = []
        hostedservice = {}
        hostedservice['CreationClassName'] = (
            self.data.hostedservice_creationclass)
        hostedservice['SystemName'] = self.data.storage_system
        hostedservice['Name'] = self.data.storage_system
        hostedservices.append(hostedservice)
        return hostedservices

    def _enum_policycapabilities(self):
        policycapabilities = []
        policycapability = {}
        policycapability['CreationClassName'] = (
            self.data.policycapability_creationclass)
        policycapability['SystemName'] = self.data.storage_system

        propertiesList = []
        CIMProperty = {'is_array': True}
        properties = {u'SupportedTierFeatures': CIMProperty}
        propertiesList.append(properties)
        policycapability['Properties'] = propertiesList

        policycapabilities.append(policycapability)

        return policycapabilities

    def _enum_policyrules(self):
        policyrules = []
        policyrule = {}
        policyrule['CreationClassName'] = self.data.policyrule_creationclass
        policyrule['SystemName'] = self.data.storage_system
        policyrule['PolicyRuleName'] = self.data.policyrule
        policyrules.append(policyrule)
        return policyrules

    def _enum_assoctierpolicy(self):
        assoctierpolicies = []
        assoctierpolicy = {}
        assoctierpolicy['CreationClassName'] = (
            self.data.assoctierpolicy_creationclass)
        assoctierpolicies.append(assoctierpolicy)
        return assoctierpolicies

    def _enum_storagepool(self):
        storagepools = []
        storagepool = {}
        storagepool['CreationClassName'] = self.data.storagepool_creationclass
        storagepool['InstanceID'] = self.data.storagepoolid
        storagepool['ElementName'] = 'gold'
        storagepools.append(storagepool)
        return storagepools

    def _enum_srpstoragepool(self):
        storagepools = []
        storagepool = {}
        storagepool['CreationClassName'] = (
            self.data.srpstoragepool_creationclass)
        storagepool['InstanceID'] = 'SYMMETRIX-+-000197200056-+-SRP_1'
        storagepool['ElementName'] = 'SRP_1'
        storagepools.append(storagepool)
        return storagepools

    def _enum_storagepoolcapabilities(self):
        storagepoolcaps = []
        storagepoolcap = {}
        storagepoolcap['CreationClassName'] = 'Symm_StoragePoolCapabilities'
        storagepoolcap['InstanceID'] = 'SYMMETRIX-+-000197200056-+-SRP_1'
        storagepoolcaps.append(storagepoolcap)
        return storagepoolcaps

    def _enum_storagesettings(self):
        storagesettings = []
        storagesetting_bronze = {}
        storagesetting_bronze['CreationClassName'] = 'CIM_StoragePoolSetting'
        storagesetting_bronze['InstanceID'] = (
            'SYMMETRIX-+-000197200056-+-SBronze:'
            'DSS-+-F-+-0-+-SR-+-SRP_1')
        storagesettings.append(storagesetting_bronze)
        storagesetting_silver = {}
        storagesetting_silver['CreationClassName'] = 'CIM_StoragePoolSetting'
        storagesetting_silver['InstanceID'] = (
            'SYMMETRIX-+-000197200056-+-SSilver:'
            'DSS-+-F-+-0-+-SR-+-SRP_1')
        storagesettings.append(storagesetting_silver)
        return storagesettings

    def _enum_targetMaskingGroup(self):
        targetMaskingGroups = []
        targetMaskingGroup = {}
        targetMaskingGroup['CreationClassName'] = 'CIM_TargetMaskingGroup'
        targetMaskingGroup['ElementName'] = self.data.port_group
        targetMaskingGroups.append(targetMaskingGroup)
        return targetMaskingGroups

    def _enum_initMaskingGroup(self):
        initMaskingGroups = []
        initMaskingGroup = {}
        initMaskingGroup['CreationClassName'] = 'CIM_InitiatorMaskingGroup'
        initMaskingGroup['ElementName'] = 'myInitGroup'
        initMaskingGroups.append(initMaskingGroup)
        return initMaskingGroups

    def _enum_storagegroup(self):
        storagegroups = []
        storagegroup1 = {}
        storagegroup1['CreationClassName'] = (
            self.data.storagegroup_creationclass)
        storagegroup1['ElementName'] = self.data.storagegroupname
        storagegroups.append(storagegroup1)
        storagegroup2 = {}
        storagegroup2['CreationClassName'] = (
            self.data.storagegroup_creationclass)
        storagegroup2['ElementName'] = self.data.defaultstoragegroupname
        storagegroup2['SystemName'] = self.data.storage_system
        storagegroups.append(storagegroup2)
        storagegroup3 = {}
        storagegroup3['CreationClassName'] = (
            self.data.storagegroup_creationclass)
        storagegroup3['ElementName'] = 'OS-fakehost-SRP_1-Bronze-DSS-SG'
        storagegroups.append(storagegroup3)
        storagegroup4 = {}
        storagegroup4['CreationClassName'] = (
            self.data.storagegroup_creationclass)
        storagegroup4['ElementName'] = 'OS-SRP_1-Bronze-DSS-SG'
        storagegroups.append(storagegroup4)
        return storagegroups

    def _enum_storagevolume(self):
        storagevolumes = []
        storagevolume = {}
        storagevolume['CreationClassName'] = (
            self.data.storagevolume_creationclass)
        storagevolumes.append(storagevolume)
        return storagevolumes

    def _enum_hdwidmgmts(self):
        services = []
        srv = {}
        srv['SystemName'] = self.data.storage_system
        services.append(srv)
        return services

    def _enum_storhdwids(self):
        storhdwids = []
        hdwid = SE_StorageHardwareID()
        hdwid['CreationClassName'] = self.data.hardwareid_creationclass
        hdwid['StorageID'] = self.data.connector['wwpns'][0]
        hdwid['InstanceID'] = "W-+-" + self.data.connector['wwpns'][0]

        hdwid.path = hdwid
        storhdwids.append(hdwid)
        return storhdwids

    def _enum_storagesystems(self):
        storagesystems = []
        storagesystem = {}
        storagesystem['SystemName'] = self.data.storage_system
        storagesystem['Name'] = self.data.storage_system
        storagesystems.append(storagesystem)
        return storagesystems

    def _enum_repservcpbls(self):
        repservcpbls = []
        servcpbl = CIM_ReplicationServiceCapabilities()
        servcpbl['CreationClassName'] = 'Symm_ReplicationServiceCapabilities'
        servcpbl['InstanceID'] = self.data.storage_system
        repservcpbls.append(servcpbl)
        return repservcpbls

    def _enum_repgroups(self):
        repgroups = []
        repgroup = {}
        repgroup['CreationClassName'] = (
            self.data.replicationgroup_creationclass)
        repgroups.append(repgroup)
        return repgroups

    def _enum_fcscsiendpoint(self):
        wwns = []
        wwn = {}
        wwn['Name'] = "5000090000000000"
        wwns.append(wwn)
        return wwns

    def _enum_maskingView(self):
        maskingViews = []
        maskingView = SYMM_LunMasking()
        maskingView['CreationClassName'] = 'Symm_LunMaskingView'
        maskingView['ElementName'] = self.data.lunmaskctrl_name

        cimproperty = Fake_CIMProperty()
        cimproperty.value = self.data.lunmaskctrl_name
        properties = {u'ElementName': cimproperty}
        maskingView.properties = properties

        maskingViews.append(maskingView)
        return maskingViews

    def _enum_portgroup(self):
        portgroups = []
        portgroup = {}
        portgroup['CreationClassName'] = (
            'CIM_TargetMaskingGroup')
        portgroup['ElementName'] = self.data.port_group
        portgroups.append(portgroup)
        return portgroups

    def _enum_metavolume(self):
        return []

    def _enum_storageSyncSvSv(self):
        conn = FakeEcomConnection()
        sourceVolume = {}
        sourceVolume['CreationClassName'] = 'Symm_StorageVolume'
        sourceVolume['DeviceID'] = self.data.test_volume['device_id']
        sourceInstanceName = conn.GetInstance(sourceVolume)
        targetVolume = {}
        targetVolume['CreationClassName'] = 'Symm_StorageVolume'
        targetVolume['DeviceID'] = self.data.test_volume['device_id']
        targetInstanceName = conn.GetInstance(sourceVolume)
        svInstances = []
        svInstance = {}
        svInstance['SyncedElement'] = targetInstanceName
        svInstance['SystemElement'] = sourceInstanceName
        svInstance['CreationClassName'] = 'SE_StorageSynchronized_SV_SV'
        svInstance['PercentSynced'] = 100
        svInstance['CopyState'] = 7
        svInstances.append(svInstance)
        return svInstances

    def _enum_sw_identity(self):
        swIdentities = []
        swIdentity = {}
        swIdentity['MajorVersion'] = self.data.majorVersion
        swIdentity['MinorVersion'] = self.data.minorVersion
        swIdentity['RevisionNumber'] = self.data.revNumber
        swIdentities.append(swIdentity)
        return swIdentities

    def _enum_ipprotocolendpoint(self):
        ipprotocolendpoints = []
        ipprotocolendpoint = CIM_IPProtocolEndpoint()
        ipprotocolendpoint['CreationClassName'] = 'CIM_IPProtocolEndpoint'
        ipprotocolendpoint['SystemName'] = self.data.storage_system
        classcimproperty = Fake_CIMProperty()
        ipv4addresscimproperty = (
            classcimproperty.fake_getipv4address())
        properties = {u'IPv4Address': ipv4addresscimproperty}
        ipprotocolendpoint.properties = properties
        ipprotocolendpoint.path = ipprotocolendpoint
        ipprotocolendpoints.append(ipprotocolendpoint)
        iqnprotocolendpoint = CIM_IPProtocolEndpoint()
        iqnprotocolendpoint['CreationClassName'] = (
            'Symm_VirtualiSCSIProtocolEndpoint')
        iqnprotocolendpoint['SystemName'] = self.data.storage_system
        classcimproperty = Fake_CIMProperty()
        iqncimproperty = (
            classcimproperty.fake_getiqn())
        properties = {u'Name': iqncimproperty}
        iqnprotocolendpoint.properties = properties
        iqnprotocolendpoint.path = iqnprotocolendpoint
        ipprotocolendpoints.append(iqnprotocolendpoint)
        return ipprotocolendpoints

    def _enum_arraychassis(self):
        arraychassiss = []
        arraychassis = Symm_ArrayChassis()
        arraychassis['CreationClassName'] = (
            'Symm_ArrayChassis')
        arraychassis['SystemName'] = self.data.storage_system_v3
        arraychassis['Tag'] = self.data.storage_system_v3
        cimproperty = Fake_CIMProperty()
        cimproperty.value = 'VMAX250F'
        properties = {u'Model': cimproperty}
        arraychassis.properties = properties
        arraychassiss.append(arraychassis)
        return arraychassiss

    def _default_enum(self):
        names = []
        name = {}
        name['Name'] = 'default'
        names.append(name)
        return names


class VMAXISCSIDriverNoFastTestCase(test.TestCase):
    def setUp(self):

        self.data = VMAXCommonData()

        self.tempdir = tempfile.mkdtemp()
        super(VMAXISCSIDriverNoFastTestCase, self).setUp()
        self.config_file_path = None
        self.create_fake_config_file_no_fast()
        self.addCleanup(self._cleanup)
        configuration = conf.Configuration(None)
        configuration.append_config_values = mock.Mock(return_value=0)
        configuration.config_group = 'ISCSINoFAST'
        configuration.cinder_emc_config_file = self.config_file_path
        self.mock_object(configuration, 'safe_get',
                         self.fake_safe_get({'driver_use_ssl':
                                             True,
                                             'volume_backend_name':
                                             'ISCSINoFAST'}))
        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         self.fake_is_v3)
        self.mock_object(utils.VMAXUtils, '_is_sync_complete',
                         return_value=True)
        self.mock_object(cinder_utils, 'get_bool_param',
                         return_value=False)
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    def fake_safe_get(self, values):
        def _safe_get(key):
            return values.get(key)
        return _safe_get

    def create_fake_config_file_no_fast(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)
        doc = self.add_array_info(doc, emc)
        filename = 'cinder_emc_config_ISCSINoFAST.xml'
        self.config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()

    def create_fake_config_file_no_fast_with_interval_retries(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)
        doc = self.add_array_info(doc, emc)
        doc = self.add_interval_and_retries(doc, emc)
        filename = 'cinder_emc_config_ISCSINoFAST_int_ret.xml'
        config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()
        return config_file_path

    def create_fake_config_file_no_fast_with_interval(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)
        doc = self.add_array_info(doc, emc)
        doc = self.add_interval_only(doc, emc)
        filename = 'cinder_emc_config_ISCSINoFAST_int.xml'
        config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()
        return config_file_path

    def create_fake_config_file_no_fast_with_retries(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)
        doc = self.add_array_info(doc, emc)
        doc = self.add_retries_only(doc, emc)
        filename = 'cinder_emc_config_ISCSINoFAST_ret.xml'
        config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()
        return config_file_path

    def add_array_info(self, doc, emc):
        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("gold")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)
        return doc

    def add_interval_and_retries(self, doc, emc):
        interval = doc.createElement("Interval")
        intervaltext = doc.createTextNode("5")
        emc.appendChild(interval)
        interval.appendChild(intervaltext)

        retries = doc.createElement("Retries")
        retriestext = doc.createTextNode("40")
        emc.appendChild(retries)
        retries.appendChild(retriestext)
        return doc

    def add_interval_only(self, doc, emc):
        interval = doc.createElement("Interval")
        intervaltext = doc.createTextNode("20")
        emc.appendChild(interval)
        interval.appendChild(intervaltext)
        return doc

    def add_retries_only(self, doc, emc):
        retries = doc.createElement("Retries")
        retriestext = doc.createTextNode("70")
        emc.appendChild(retries)
        retries.appendChild(retriestext)
        return doc

    # fix for https://bugs.launchpad.net/cinder/+bug/1364232
    def create_fake_config_file_1364232(self):
        filename = 'cinder_emc_config_1364232.xml'
        config_file_1364232 = self.tempdir + '/' + filename
        text_file = open(config_file_1364232, "w")
        text_file.write("<?xml version='1.0' encoding='UTF-8'?>\n<EMC>\n"
                        "<EcomServerIp>10.10.10.10</EcomServerIp>\n"
                        "<EcomServerPort>5988</EcomServerPort>\n"
                        "<EcomUserName>user\t</EcomUserName>\n"
                        "<EcomPassword>password</EcomPassword>\n"
                        "<PortGroups><PortGroup>OS-PORTGROUP1-PG"
                        "</PortGroup><PortGroup>OS-PORTGROUP2-PG"
                        "                </PortGroup>\n"
                        "<PortGroup>OS-PORTGROUP3-PG</PortGroup>"
                        "<PortGroup>OS-PORTGROUP4-PG</PortGroup>"
                        "</PortGroups>\n<Array>000198700439"
                        "              \n</Array>\n<Pool>FC_SLVR1\n"
                        "</Pool>\n<FastPolicy>SILVER1</FastPolicy>\n"
                        "</EMC>")
        text_file.close()
        return config_file_1364232

    def fake_ecom_connection(self):
        conn = FakeEcomConnection()
        return conn

    def fake_is_v3(self, conn, serialNumber):
        return False

    def test_slo_empty_tag(self):
        filename = 'cinder_emc_config_slo_empty_tag'
        tempdir = tempfile.mkdtemp()
        config_file = tempdir + '/' + filename
        text_file = open(config_file, "w")
        text_file.write("<?xml version='1.0' encoding='UTF-8'?>\n<EMC>\n"
                        "<EcomServerIp>10.10.10.10</EcomServerIp>\n"
                        "<EcomServerPort>5988</EcomServerPort>\n"
                        "<EcomUserName>user</EcomUserName>\n"
                        "<EcomPassword>password</EcomPassword>\n"
                        "<PortGroups>\n"
                        "<PortGroup>OS-PORTGROUP1-PG</PortGroup>\n"
                        "</PortGroups>\n"
                        "<Pool>SRP_1</Pool>\n"
                        "<Slo></Slo>\n"
                        "<Workload></Workload>\n"
                        "</EMC>")
        text_file.close()

        arrayInfo = self.driver.utils.parse_file_to_get_array_map(config_file)
        self.assertIsNone(arrayInfo[0]['SLO'])
        self.assertIsNone(arrayInfo[0]['Workload'])
        bExists = os.path.exists(config_file)
        if bExists:
            os.remove(config_file)

    def test_filter_list(self):
        portgroupnames = ['pg3', 'pg1', 'pg4', 'pg2']
        portgroupnames = (
            self.driver.common.utils._filter_list(portgroupnames))
        self.assertEqual(4, len(portgroupnames))
        self.assertEqual(['pg1', 'pg2', 'pg3', 'pg4'], sorted(portgroupnames))

        portgroupnames = ['pg1']
        portgroupnames = (
            self.driver.common.utils._filter_list(portgroupnames))
        self.assertEqual(1, len(portgroupnames))
        self.assertEqual(['pg1'], portgroupnames)

        portgroupnames = ['only_pg', '', '', '', '', '']
        portgroupnames = (
            self.driver.common.utils._filter_list(portgroupnames))
        self.assertEqual(1, len(portgroupnames))
        self.assertEqual(['only_pg'], portgroupnames)

    def test_get_random_pg_from_list(self):
        portGroupNames = ['pg1', 'pg2', 'pg3', 'pg4']
        portGroupName = (
            self.driver.common.utils.get_random_pg_from_list(portGroupNames))
        self.assertIn('pg', portGroupName)

        portGroupNames = ['pg1']
        portGroupName = (
            self.driver.common.utils.get_random_pg_from_list(portGroupNames))
        self.assertEqual('pg1', portGroupName)

    def test_get_random_portgroup(self):
        # 4 portgroups
        data = ("<?xml version='1.0' encoding='UTF-8'?>\n<EMC>\n"
                "<PortGroups>"
                "<PortGroup>OS-PG1</PortGroup>\n"
                "<PortGroup>OS-PG2</PortGroup>\n"
                "<PortGroup>OS-PG3</PortGroup>\n"
                "<PortGroup>OS-PG4</PortGroup>\n"
                "</PortGroups>"
                "</EMC>")
        dom = minidom.parseString(data)
        portgroup = self.driver.common.utils._get_random_portgroup(dom)
        self.assertIn('OS-PG', portgroup)

        # Duplicate portgroups
        data = ("<?xml version='1.0' encoding='UTF-8'?>\n<EMC>\n"
                "<PortGroups>"
                "<PortGroup>OS-PG1</PortGroup>\n"
                "<PortGroup>OS-PG1</PortGroup>\n"
                "<PortGroup>OS-PG1</PortGroup>\n"
                "<PortGroup>OS-PG2</PortGroup>\n"
                "</PortGroups>"
                "</EMC>")
        dom = minidom.parseString(data)
        portgroup = self.driver.common.utils._get_random_portgroup(dom)
        self.assertIn('OS-PG', portgroup)

    def test_get_random_portgroup_exception(self):
        # Missing PortGroup values
        data = ("<?xml version='1.0' encoding='UTF-8'?>\n<EMC>\n"
                "<PortGroups>"
                "<PortGroup></PortGroup>\n"
                "<PortGroup></PortGroup>\n"
                "</PortGroups>"
                "</EMC>")
        dom = minidom.parseString(data)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common.utils._get_random_portgroup, dom)

        # Missing portgroups
        data = ("<?xml version='1.0' encoding='UTF-8'?>\n<EMC>\n"
                "<PortGroups>"
                "</PortGroups>"
                "</EMC>")
        dom = minidom.parseString(data)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common.utils._get_random_portgroup, dom)

    def test_get_correct_port_group(self):
        self.driver.common.conn = self.fake_ecom_connection()
        maskingViewInstanceName = {'CreationClassName': 'Symm_LunMaskingView',
                                   'ElementName': 'OS-fakehost-gold-I-MV',
                                   'SystemName': 'SYMMETRIX+000195900551'}
        deviceinfodict = {'controller': maskingViewInstanceName}
        portgroupname = self.driver.common._get_correct_port_group(
            deviceinfodict, self.data.storage_system)
        self.assertEqual('OS-portgroup-PG', portgroupname)

    def test_generate_unique_trunc_pool(self):
        pool_under_16_chars = 'pool_under_16'
        pool1 = self.driver.utils.generate_unique_trunc_pool(
            pool_under_16_chars)
        self.assertEqual(pool_under_16_chars, pool1)

        pool_over_16_chars = (
            'pool_over_16_pool_over_16')
        # Should generate truncated string first 8 chars and
        # last 7 chars
        pool2 = self.driver.utils.generate_unique_trunc_pool(
            pool_over_16_chars)
        self.assertEqual('pool_ove_over_16', pool2)

    def test_generate_unique_trunc_host(self):
        host_under_38_chars = 'host_under_38_chars'
        host1 = self.driver.utils.generate_unique_trunc_host(
            host_under_38_chars)
        self.assertEqual(host_under_38_chars, host1)

        host_over_38_chars = (
            'host_over_38_chars_host_over_38_chars_host_over_38_chars')
        # Check that the same md5 value is retrieved from multiple calls
        host2 = self.driver.utils.generate_unique_trunc_host(
            host_over_38_chars)
        host3 = self.driver.utils.generate_unique_trunc_host(
            host_over_38_chars)
        self.assertEqual(host2, host3)

    def test_find_ip_protocol_endpoints(self):
        conn = self.fake_ecom_connection()
        endpoint = self.driver.common._find_ip_protocol_endpoints(
            conn, self.data.storage_system, self.data.port_group)
        self.assertEqual('10.10.10.10', endpoint[0]['ip'])

    def test_find_device_number(self):
        host = 'fakehost'
        data, __, __ = (
            self.driver.common.find_device_number(self.data.test_volume,
                                                  host))
        self.assertEqual('OS-fakehost-MV', data['maskingview'])

    @mock.patch.object(
        FakeEcomConnection,
        'ReferenceNames',
        return_value=[])
    def test_find_device_number_false(self, mock_ref_name):
        host = 'bogushost'
        data, __, __ = (
            self.driver.common.find_device_number(self.data.test_volume,
                                                  host))
        self.assertFalse(data)

    def test_find_device_number_long_host(self):
        # Long host name
        host = 'myhost.mydomain.com'
        data, __, __ = (
            self.driver.common.find_device_number(self.data.test_volume,
                                                  host))
        self.assertEqual('OS-myhost-MV', data['maskingview'])

    def test_find_device_number_short_name_over_38_chars(self):
        # short name over 38 chars
        host = 'myShortnameIsOverThirtyEightCharactersLong'
        host = self.driver.common.utils.generate_unique_trunc_host(host)
        amended = 'OS-' + host + '-MV'
        v2_host_over_38 = self.data.test_volume.copy()
        # Pool aware scheduler enabled
        v2_host_over_38['host'] = host
        data, __, __ = (
            self.driver.common.find_device_number(v2_host_over_38,
                                                  host))
        self.assertEqual(amended, data['maskingview'])

    def test_unbind_and_get_volume_from_storage_pool(self):
        conn = self.fake_ecom_connection()
        common = self.driver.common
        common.utils.is_volume_bound_to_pool = mock.Mock(
            return_value='False')
        storageConfigService = (
            common.utils.find_storage_configuration_service(
                conn, self.data.storage_system))
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeName = "unbind-vol"
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': False}
        volumeInstance = (
            common._unbind_and_get_volume_from_storage_pool(
                conn, storageConfigService,
                volumeInstanceName, volumeName, extraSpecs))
        self.assertEqual(self.data.storage_system,
                         volumeInstance['SystemName'])
        self.assertEqual('1', volumeInstance['ElementName'])

    def test_create_hardware_ids(self):
        conn = self.fake_ecom_connection()
        connector = {
            'ip': '10.0.0.2',
            'initiator': self.data.iscsi_initiator,
            'host': 'fakehost'}
        initiatorNames = (
            self.driver.common.masking._find_initiator_names(conn, connector))
        storageHardwareIDInstanceNames = (
            self.driver.common.masking._create_hardware_ids(
                conn, initiatorNames, self.data.storage_system))
        self.assertEqual(self.data.iscsi_initiator,
                         storageHardwareIDInstanceNames[0])

    def test_get_pool_instance_and_system_name(self):
        conn = self.fake_ecom_connection()
        # V2 - old '+' separator
        storagesystem = {}
        storagesystem['SystemName'] = self.data.storage_system
        storagesystem['Name'] = self.data.storage_system
        pools = conn.EnumerateInstanceNames("EMC_VirtualProvisioningPool")
        poolname = 'gold'
        poolinstancename, systemname = (
            self.driver.common.utils._get_pool_instance_and_system_name(
                conn, pools, storagesystem, poolname))
        self.assertEqual(self.data.storage_system, systemname)
        self.assertEqual(self.data.storagepoolid,
                         poolinstancename['InstanceID'])
        # V3 - note: V2 can also have the '-+-' separator
        storagesystem = {}
        storagesystem['SystemName'] = self.data.storage_system_v3
        storagesystem['Name'] = self.data.storage_system_v3
        pools = conn.EnumerateInstanceNames('Symm_SRPStoragePool')
        poolname = 'SRP_1'
        poolinstancename, systemname = (
            self.driver.common.utils._get_pool_instance_and_system_name(
                conn, pools, storagesystem, poolname))
        self.assertEqual(self.data.storage_system_v3, systemname)
        self.assertEqual('SYMMETRIX-+-000197200056-+-SRP_1',
                         poolinstancename['InstanceID'])
        # Invalid poolname
        poolname = 'bogus'
        poolinstancename, systemname = (
            self.driver.common.utils._get_pool_instance_and_system_name(
                conn, pools, storagesystem, poolname))
        self.assertIsNone(poolinstancename)
        self.assertEqual(self.data.storage_system_v3, systemname)

    def test_get_hardware_type(self):
        iqn_initiator = 'iqn.1992-04.com.emc: 50000973f006dd80'
        hardwaretypeid = (
            self.driver.utils._get_hardware_type(iqn_initiator))
        self.assertEqual(5, hardwaretypeid)
        wwpn_initiator = '123456789012345'
        hardwaretypeid = (
            self.driver.utils._get_hardware_type(wwpn_initiator))
        self.assertEqual(2, hardwaretypeid)
        bogus_initiator = 'bogus'
        hardwaretypeid = (
            self.driver.utils._get_hardware_type(bogus_initiator))
        self.assertEqual(0, hardwaretypeid)

    def test_check_if_rollback_action_for_masking_required(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': False,
                      'storagetype:fastpolicy': 'GOLD1'}

        vol = EMC_StorageVolume()
        vol['name'] = self.data.test_volume['name']
        vol['CreationClassName'] = 'Symm_StorageVolume'
        vol['ElementName'] = self.data.test_volume['id']
        vol['DeviceID'] = self.data.test_volume['device_id']
        vol['Id'] = self.data.test_volume['id']
        vol['SystemName'] = self.data.storage_system
        vol['NumberOfBlocks'] = self.data.test_volume['NumberOfBlocks']
        vol['BlockSize'] = self.data.test_volume['BlockSize']

        # Added vol to vol.path
        vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        vol.path = vol
        vol.path.classname = vol['CreationClassName']

        rollbackDict = {}
        rollbackDict['isV3'] = False
        rollbackDict['defaultStorageGroupInstanceName'] = (
            self.data.default_storage_group)
        rollbackDict['sgName'] = self.data.storagegroupname
        rollbackDict['sgGroupName'] = self.data.storagegroupname
        rollbackDict['volumeName'] = 'vol1'
        rollbackDict['fastPolicyName'] = 'GOLD1'
        rollbackDict['volumeInstance'] = vol
        rollbackDict['controllerConfigService'] = controllerConfigService
        rollbackDict['extraSpecs'] = extraSpecs
        rollbackDict['igGroupName'] = self.data.initiatorgroup_name
        rollbackDict['connector'] = self.data.connector
        # Path 1 - The volume is in another storage group that isn't the
        # default storage group
        expectedmessage = (_("Rollback - Volume in another storage "
                             "group besides default storage group."))
        message = (
            self.driver.common.masking.
            _check_if_rollback_action_for_masking_required(
                conn, rollbackDict))
        self.assertEqual(expectedmessage, message)
        # Path 2 - The volume is not in any storage group
        rollbackDict['sgName'] = 'sq_not_exist'
        rollbackDict['sgGroupName'] = 'sq_not_exist'
        expectedmessage = (_("V2 rollback, volume is not in any storage "
                             "group."))
        message = (
            self.driver.common.masking.
            _check_if_rollback_action_for_masking_required(
                conn, rollbackDict))
        self.assertEqual(expectedmessage, message)

    def test_migrate_cleanup(self):
        conn = self.fake_ecom_connection()
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': False,
                      'storagetype:fastpolicy': 'GOLD1'}

        vol = EMC_StorageVolume()
        vol['name'] = self.data.test_volume['name']
        vol['CreationClassName'] = 'Symm_StorageVolume'
        vol['ElementName'] = self.data.test_volume['id']
        vol['DeviceID'] = self.data.test_volume['device_id']
        vol['Id'] = self.data.test_volume['id']
        vol['SystemName'] = self.data.storage_system
        vol['NumberOfBlocks'] = self.data.test_volume['NumberOfBlocks']
        vol['BlockSize'] = self.data.test_volume['BlockSize']

        # Added vol to vol.path
        vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        vol.path = vol
        vol.path.classname = vol['CreationClassName']
        # The volume is already belong to default storage group
        return_to_default = self.driver.common._migrate_cleanup(
            conn, vol, self.data.storage_system, 'GOLD1',
            vol['name'], extraSpecs)
        self.assertFalse(return_to_default)
        # The volume does not belong to default storage group
        return_to_default = self.driver.common._migrate_cleanup(
            conn, vol, self.data.storage_system, 'BRONZE1',
            vol['name'], extraSpecs)
        self.assertTrue(return_to_default)

    @unittest.skip("Skip until bug #1578986 is fixed")
    def _test_wait_for_job_complete(self):
        myjob = SE_ConcreteJob()
        myjob.classname = 'SE_ConcreteJob'
        myjob['InstanceID'] = '9999'
        myjob['status'] = 'success'
        myjob['type'] = 'type'
        myjob['CreationClassName'] = 'SE_ConcreteJob'
        myjob['Job'] = myjob
        conn = self.fake_ecom_connection()

        self.driver.utils._is_job_finished = mock.Mock(
            return_value=True)
        rc, errordesc = self.driver.utils.wait_for_job_complete(conn, myjob)
        self.assertEqual(0, rc)
        self.assertIsNone(errordesc)
        self.driver.utils._is_job_finished.assert_called_once_with(
            conn, myjob)
        self.assertTrue(self.driver.utils._is_job_finished.return_value)
        self.driver.utils._is_job_finished.reset_mock()

        rc, errordesc = self.driver.utils.wait_for_job_complete(conn, myjob)
        self.assertEqual(0, rc)
        self.assertIsNone(errordesc)

    @unittest.skip("Skip until bug #1578986 is fixed")
    def _test_wait_for_job_complete_bad_job_state(self):
        myjob = SE_ConcreteJob()
        myjob.classname = 'SE_ConcreteJob'
        myjob['InstanceID'] = '9999'
        myjob['status'] = 'success'
        myjob['type'] = 'type'
        myjob['CreationClassName'] = 'SE_ConcreteJob'
        myjob['Job'] = myjob
        conn = self.fake_ecom_connection()
        self.driver.utils._is_job_finished = mock.Mock(
            return_value=True)
        self.driver.utils._verify_job_state = mock.Mock(
            return_value=(-1, 'Job finished with an error'))
        rc, errordesc = self.driver.utils.wait_for_job_complete(conn, myjob)
        self.assertEqual(-1, rc)
        self.assertEqual('Job finished with an error', errordesc)

    @unittest.skip("Skip until bug #1578986 is fixed")
    def _test_wait_for_sync(self):
        mysync = 'fakesync'
        conn = self.fake_ecom_connection()

        self.driver.utils._is_sync_complete = mock.Mock(
            return_value=True)
        self.driver.utils._get_interval_in_secs = mock.Mock(return_value=0)
        rc = self.driver.utils.wait_for_sync(conn, mysync)
        self.assertIsNotNone(rc)
        self.driver.utils._is_sync_complete.assert_called_once_with(
            conn, mysync)
        self.assertTrue(self.driver.utils._is_sync_complete.return_value)
        self.driver.utils._is_sync_complete.reset_mock()

        rc = self.driver.utils.wait_for_sync(conn, mysync)
        self.assertIsNotNone(rc)

    @unittest.skip("Skip until bug #1578986 is fixed")
    def test_wait_for_sync_extra_specs(self):
        mysync = 'fakesync'
        conn = self.fake_ecom_connection()
        file_name = (
            self.create_fake_config_file_no_fast_with_interval_retries())
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        pool = 'gold+1234567891011'
        arrayInfo = self.driver.utils.parse_file_to_get_array_map(
            self.config_file_path)
        poolRec = self.driver.utils.extract_record(arrayInfo, pool)
        extraSpecs = self.driver.common._set_v2_extra_specs(extraSpecs,
                                                            poolRec)

        self.driver.utils._is_sync_complete = mock.Mock(
            return_value=True)
        self.driver.utils._get_interval_in_secs = mock.Mock(return_value=0)
        rc = self.driver.utils.wait_for_sync(conn, mysync, extraSpecs)
        self.assertIsNotNone(rc)
        self.driver.utils._is_sync_complete.assert_called_once_with(
            conn, mysync)
        self.assertTrue(self.driver.utils._is_sync_complete.return_value)
        self.assertEqual(40,
                         self.driver.utils._get_max_job_retries(extraSpecs))
        self.assertEqual(5,
                         self.driver.utils._get_interval_in_secs(extraSpecs))
        self.driver.utils._is_sync_complete.reset_mock()

        rc = self.driver.utils.wait_for_sync(conn, mysync)
        self.assertIsNotNone(rc)
        bExists = os.path.exists(file_name)
        if bExists:
            os.remove(file_name)

    # Bug 1395830: _find_lun throws exception when lun is not found.
    def test_find_lun(self):
        keybindings = {'CreationClassName': u'Symm_StorageVolume',
                       'SystemName': u'SYMMETRIX+000195900551',
                       'DeviceID': u'1',
                       'SystemCreationClassName': u'Symm_StorageSystem'}
        provider_location = {'classname': 'Symm_StorageVolume',
                             'keybindings': keybindings}
        volume = EMC_StorageVolume()
        volume['name'] = 'vol1'
        volume['id'] = '1'
        volume['provider_location'] = six.text_type(provider_location)

        self.driver.common.conn = self.driver.common._get_ecom_connection()
        findlun = self.driver.common._find_lun(volume)
        getinstance = self.driver.common.conn._getinstance_storagevolume(
            keybindings)
        # Found lun.
        self.assertEqual(getinstance, findlun)

        keybindings2 = {'CreationClassName': u'Symm_StorageVolume',
                        'SystemName': u'SYMMETRIX+000195900551',
                        'DeviceID': u'9',
                        'SystemCreationClassName': u'Symm_StorageSystem'}
        provider_location2 = {'classname': 'Symm_StorageVolume',
                              'keybindings': keybindings2}
        volume2 = EMC_StorageVolume()
        volume2['name'] = 'myVol'
        volume2['id'] = 'myVol'
        volume2['provider_location'] = six.text_type(provider_location2)
        verify_orig = self.driver.common.conn.GetInstance
        self.driver.common.conn.GetInstance = mock.Mock(
            return_value=None)
        findlun2 = self.driver.common._find_lun(volume2)
        # Not found.
        self.assertIsNone(findlun2)
        self.driver.utils.get_instance_name(
            provider_location2['classname'],
            keybindings2)
        self.driver.common.conn.GetInstance.assert_called_once_with(
            keybindings2)
        self.driver.common.conn.GetInstance.reset_mock()
        self.driver.common.conn.GetInstance = verify_orig

        keybindings3 = {'CreationClassName': u'Symm_StorageVolume',
                        'SystemName': u'SYMMETRIX+000195900551',
                        'DeviceID': u'9999',
                        'SystemCreationClassName': u'Symm_StorageSystem'}
        provider_location3 = {'classname': 'Symm_StorageVolume',
                              'keybindings': keybindings3}
        instancename3 = self.driver.utils.get_instance_name(
            provider_location3['classname'],
            keybindings3)
        # Error other than not found.
        arg = 9999, "test_error"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common.utils.process_exception_args,
                          arg, instancename3)

    # Bug 1403160 - make sure the masking view is cleanly deleted
    def test_last_volume_delete_masking_view(self):
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        maskingViewInstanceName = (
            self.driver.common.masking._find_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))

        maskingViewName = conn.GetInstance(
            maskingViewInstanceName)['ElementName']

        # Deleting Masking View failed
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.common.masking._last_volume_delete_masking_view,
            conn, controllerConfigService, maskingViewInstanceName,
            maskingViewName, extraSpecs)

        # Deleting Masking view successful
        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        self.driver.common.masking._last_volume_delete_masking_view(
            conn, controllerConfigService, maskingViewInstanceName,
            maskingViewName, extraSpecs)

    # Bug 1403160 - make sure the storage group is cleanly deleted
    def test_remove_last_vol_and_delete_sg(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        storageGroupName = self.data.storagegroupname
        storageGroupInstanceName = (
            self.driver.utils.find_storage_masking_group(
                conn, controllerConfigService, storageGroupName))

        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeName = "1403160-Vol"
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': False}

        # Deleting Storage Group failed
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.common.masking._remove_last_vol_and_delete_sg,
            conn, controllerConfigService, storageGroupInstanceName,
            storageGroupName, volumeInstanceName, volumeName, extraSpecs)

        # Deleting Storage group successful
        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        self.driver.common.masking._remove_last_vol_and_delete_sg(
            conn, controllerConfigService, storageGroupInstanceName,
            storageGroupName, volumeInstanceName, volumeName, extraSpecs)

    # Bug 1504192 - if the last volume is being unmapped and the masking view
    # goes away, cleanup the initiators and associated initiator group.
    def test_delete_initiators_from_initiator_group(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        initiatorGroupName = self.data.initiatorgroup_name
        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        conn.InvokeMethod = mock.Mock(return_value=1)
        # Deletion of initiators failed.
        self.driver.common.masking._delete_initiators_from_initiator_group(
            conn, controllerConfigService, initiatorGroupInstanceName,
            initiatorGroupName)
        conn.InvokeMethod = mock.Mock(return_value=0)
        # Deletion of initiators successful.
        self.driver.common.masking._delete_initiators_from_initiator_group(
            conn, controllerConfigService, initiatorGroupInstanceName,
            initiatorGroupName)

    # Bug 1504192 - if the last volume is being unmapped and the masking view
    # goes away, cleanup the initiators and associated initiator group.
    def test_last_volume_delete_initiator_group_exception(self):
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        conn = self.fake_ecom_connection()
        host = self.data.lunmaskctrl_name.split("-")[1]
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        job = {
            'Job': {'InstanceID': '9999', 'status': 'success', 'type': None}}
        conn.InvokeMethod = mock.Mock(return_value=(4096, job))
        self.driver.common.masking.get_masking_views_by_initiator_group = (
            mock.Mock(return_value=[]))
        self.driver.common.masking._delete_initiators_from_initiator_group = (
            mock.Mock(return_value=True))
        self.driver.common.masking.utils.wait_for_job_complete = (
            mock.Mock(return_value=(2, 'failure')))
        # Exception occurrs while deleting the initiator group.
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.common.masking._last_volume_delete_initiator_group,
            conn, controllerConfigService, initiatorGroupInstanceName,
            extraSpecs, host)

    # Bug 1504192 - if the last volume is being unmapped and the masking view
    # goes away, cleanup the initiators and associated initiator group.
    def test_last_volume_delete_initiator_group(self):
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        conn = self.fake_ecom_connection()
        host = self.data.lunmaskctrl_name.split("-")[1]
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        initiatorGroupName = self.data.initiatorgroup_name
        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        self.assertEqual(initiatorGroupName,
                         conn.GetInstance(
                             initiatorGroupInstanceName)['ElementName'])
        # Path 1: masking view is associated with the initiator group and
        # initiator group will not be deleted.
        self.driver.common.masking._last_volume_delete_initiator_group(
            conn, controllerConfigService, initiatorGroupInstanceName,
            extraSpecs, host)
        # Path 2: initiator group name is not the default name so the
        # initiator group will not be deleted.
        initGroup2 = initiatorGroupInstanceName
        initGroup2['ElementName'] = "different-name-ig"
        self.driver.common.masking._last_volume_delete_initiator_group(
            conn, controllerConfigService, initGroup2,
            extraSpecs, host)
        # Path 3: No Masking view and IG is the default IG, so initiators
        # associated with the Initiator group and the initiator group will
        # be deleted.
        self.driver.common.masking.get_masking_views_by_initiator_group = (
            mock.Mock(return_value=[]))
        self.driver.common.masking._delete_initiators_from_initiator_group = (
            mock.Mock(return_value=True))
        self.driver.common.masking._last_volume_delete_initiator_group(
            conn, controllerConfigService, initiatorGroupInstanceName,
            extraSpecs, host)
        job = {
            'Job': {'InstanceID': '9999', 'status': 'success', 'type': None}}
        conn.InvokeMethod = mock.Mock(return_value=(4096, job))
        self.driver.common.masking.utils.wait_for_job_complete = (
            mock.Mock(return_value=(0, 'success')))
        # Deletion of initiator group is successful after waiting for job
        # to complete.
        self.driver.common.masking._last_volume_delete_initiator_group(
            conn, controllerConfigService, initiatorGroupInstanceName,
            extraSpecs, host)

    # Tests removal of last volume in a storage group V2
    def test_remove_and_reset_members(self):
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': False}
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        volumeName = "Last-Vol"
        self.driver.common.masking.get_devices_from_storage_group = mock.Mock(
            return_value=['one_value'])
        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)

        self.driver.common.masking.remove_and_reset_members(
            conn, controllerConfigService, volumeInstance,
            volumeName, extraSpecs)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_associated_masking_groups_from_device',
        return_value=VMAXCommonData.storagegroups)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_existing_instance',
        return_value=None)
    def test_remove_and_reset_members_v3(self, mock_inst, mock_sg):
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'pool': 'SRP_1',
                      'workload': 'DSS',
                      'slo': 'Bronze'}
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        volumeName = "1416035-Vol"

        self.driver.common.masking.remove_and_reset_members(
            conn, controllerConfigService, volumeInstance,
            volumeName, extraSpecs, reset=False)

    # Bug 1393555 - masking view has been deleted by another process.
    def test_find_maskingview(self):
        conn = self.fake_ecom_connection()
        foundMaskingViewInstanceName = (
            self.driver.common.masking._find_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The masking view has been found.
        self.assertEqual(
            self.data.lunmaskctrl_name,
            conn.GetInstance(foundMaskingViewInstanceName)['ElementName'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundMaskingViewInstanceName2 = (
            self.driver.common.masking._find_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The masking view has not been found.
        self.assertIsNone(foundMaskingViewInstanceName2)

    # Bug 1393555 - port group has been deleted by another process.
    def test_find_portgroup(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        foundPortGroupInstanceName = (
            self.driver.common.masking.find_port_group(
                conn, controllerConfigService, self.data.port_group))
        # The port group has been found.
        self.assertEqual(
            self.data.port_group,
            conn.GetInstance(foundPortGroupInstanceName)['ElementName'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundPortGroupInstanceName2 = (
            self.driver.common.masking.find_port_group(
                conn, controllerConfigService, self.data.port_group))
        # The port group has not been found as it has been deleted
        # externally or by another thread.
        self.assertIsNone(foundPortGroupInstanceName2)

    # Bug 1393555 - storage group has been deleted by another process.
    def test_get_storage_group_from_masking_view(self):
        conn = self.fake_ecom_connection()
        foundStorageGroupInstanceName = (
            self.driver.common.masking._get_storage_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The storage group has been found.
        self.assertEqual(
            self.data.storagegroupname,
            conn.GetInstance(foundStorageGroupInstanceName)['ElementName'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundStorageGroupInstanceName2 = (
            self.driver.common.masking._get_storage_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The storage group has not been found as it has been deleted
        # externally or by another thread.
        self.assertIsNone(foundStorageGroupInstanceName2)

    # Bug 1393555 - initiator group has been deleted by another process.
    def test_get_initiator_group_from_masking_view(self):
        conn = self.fake_ecom_connection()
        foundInitiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The initiator group has been found.
        self.assertEqual(
            self.data.initiatorgroup_name,
            conn.GetInstance(foundInitiatorGroupInstanceName)['ElementName'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundInitiatorGroupInstanceName2 = (
            self.driver.common.masking._get_storage_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The initiator group has not been found as it has been deleted
        # externally or by another thread.
        self.assertIsNone(foundInitiatorGroupInstanceName2)

    # Bug 1393555 - port group has been deleted by another process.
    def test_get_port_group_from_masking_view(self):
        conn = self.fake_ecom_connection()
        foundPortGroupInstanceName = (
            self.driver.common.masking._get_port_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The port group has been found.
        self.assertEqual(
            self.data.port_group,
            conn.GetInstance(foundPortGroupInstanceName)['ElementName'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundPortGroupInstanceName2 = (
            self.driver.common.masking._get_port_group_from_masking_view(
                conn, self.data.lunmaskctrl_name, self.data.storage_system))
        # The port group has not been found as it has been deleted
        # externally or by another thread.
        self.assertIsNone(foundPortGroupInstanceName2)

    # Bug 1393555 - initiator group has been deleted by another process.
    def test_find_initiator_group(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        foundInitiatorGroupInstanceName = (
            self.driver.common.masking._find_initiator_masking_group(
                conn, controllerConfigService, self.data.initiatorNames))
        # The initiator group has been found.
        self.assertEqual(
            self.data.initiatorgroup_name,
            conn.GetInstance(foundInitiatorGroupInstanceName)['ElementName'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundInitiatorGroupInstanceName2 = (
            self.driver.common.masking._find_initiator_masking_group(
                conn, controllerConfigService, self.data.initiatorNames))
        # The initiator group has not been found as it has been deleted
        # externally or by another thread.
        self.assertIsNone(foundInitiatorGroupInstanceName2)

    # Bug 1393555 - hardware id has been deleted by another process.
    def test_get_storage_hardware_id_instance_names(self):
        conn = self.fake_ecom_connection()
        foundHardwareIdInstanceNames = (
            self.driver.common.masking._get_storage_hardware_id_instance_names(
                conn, self.data.initiatorNames, self.data.storage_system))
        # The hardware id list has been found.
        self.assertEqual(
            '123456789012345',
            conn.GetInstance(
                foundHardwareIdInstanceNames[0])['StorageID'])

        self.driver.common.masking.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundHardwareIdInstanceNames2 = (
            self.driver.common.masking._get_storage_hardware_id_instance_names(
                conn, self.data.initiatorNames, self.data.storage_system))
        # The hardware id list has not been found as it has been removed
        # externally.
        self.assertEqual(0, len(foundHardwareIdInstanceNames2))

    # Bug 1393555 - controller has been deleted by another process.
    def test_find_lunmasking_scsi_protocol_controller(self):
        self.driver.common.conn = self.fake_ecom_connection()
        foundControllerInstanceName = (
            self.driver.common._find_lunmasking_scsi_protocol_controller(
                self.data.storage_system, self.data.connector))
        # The controller has been found.
        self.assertEqual(
            'OS-fakehost-gold-I-MV',
            self.driver.common.conn.GetInstance(
                foundControllerInstanceName)['ElementName'])

        self.driver.common.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundControllerInstanceName2 = (
            self.driver.common._find_lunmasking_scsi_protocol_controller(
                self.data.storage_system, self.data.connector))
        # The controller has not been found as it has been removed
        # externally.
        self.assertIsNone(foundControllerInstanceName2)

    # Bug 1393555 - storage group has been deleted by another process.
    def test_get_policy_default_storage_group(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        foundStorageMaskingGroupInstanceName = (
            self.driver.common.fast.get_policy_default_storage_group(
                conn, controllerConfigService, 'OS_default'))
        # The storage group has been found.
        self.assertEqual(
            'OS_default_GOLD1_SG',
            conn.GetInstance(
                foundStorageMaskingGroupInstanceName)['ElementName'])

        self.driver.common.fast.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundStorageMaskingGroupInstanceName2 = (
            self.driver.common.fast.get_policy_default_storage_group(
                conn, controllerConfigService, 'OS_default'))
        # The storage group has not been found as it has been removed
        # externally.
        self.assertIsNone(foundStorageMaskingGroupInstanceName2)

    # Bug 1393555 - policy has been deleted by another process.
    def test_get_capacities_associated_to_policy(self):
        conn = self.fake_ecom_connection()
        (total_capacity_gb, free_capacity_gb, provisioned_capacity_gb,
         array_max_over_subscription) = (
            self.driver.common.fast.get_capacities_associated_to_policy(
                conn, self.data.storage_system, self.data.policyrule))
        # The capacities associated to the policy have been found.
        self.assertEqual(self.data.totalmanagedspace_gbs, total_capacity_gb)
        self.assertEqual(self.data.remainingmanagedspace_gbs, free_capacity_gb)

        self.driver.common.fast.utils.get_existing_instance = mock.Mock(
            return_value=None)
        (total_capacity_gb_2, free_capacity_gb_2, provisioned_capacity_gb_2,
         array_max_over_subscription_2) = (
            self.driver.common.fast.get_capacities_associated_to_policy(
                conn, self.data.storage_system, self.data.policyrule))
        # The capacities have not been found as the policy has been
        # removed externally.
        self.assertEqual(0, total_capacity_gb_2)
        self.assertEqual(0, free_capacity_gb_2)
        self.assertEqual(0, provisioned_capacity_gb_2)

    # Bug 1393555 - storage group has been deleted by another process.
    def test_find_storage_masking_group(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        foundStorageMaskingGroupInstanceName = (
            self.driver.common.utils.find_storage_masking_group(
                conn, controllerConfigService, self.data.storagegroupname))
        # The storage group has been found.
        self.assertEqual(
            self.data.storagegroupname,
            conn.GetInstance(
                foundStorageMaskingGroupInstanceName)['ElementName'])

        self.driver.common.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundStorageMaskingGroupInstanceName2 = (
            self.driver.common.utils.find_storage_masking_group(
                conn, controllerConfigService, self.data.storagegroupname))
        # The storage group has not been found as it has been removed
        # externally.
        self.assertIsNone(foundStorageMaskingGroupInstanceName2)

    # Bug 1393555 - pool has been deleted by another process.
    def test_get_pool_by_name(self):
        conn = self.fake_ecom_connection()

        foundPoolInstanceName = self.driver.common.utils.get_pool_by_name(
            conn, self.data.poolname, self.data.storage_system)
        # The pool has been found.
        self.assertEqual(
            self.data.poolname,
            conn.GetInstance(foundPoolInstanceName)['ElementName'])

        self.driver.common.utils.get_existing_instance = mock.Mock(
            return_value=None)
        foundPoolInstanceName2 = self.driver.common.utils.get_pool_by_name(
            conn, self.data.poolname, self.data.storage_system)
        # The pool has not been found as it has been removed externally.
        self.assertIsNone(foundPoolInstanceName2)

    def test_get_volume_stats_1364232(self):
        file_name = self.create_fake_config_file_1364232()

        arrayInfo = self.driver.utils.parse_file_to_get_array_map(file_name)
        self.assertEqual(
            '000198700439', arrayInfo[0]['SerialNumber'])
        self.assertEqual(
            'FC_SLVR1', arrayInfo[0]['PoolName'])
        self.assertEqual(
            'SILVER1', arrayInfo[0]['FastPolicy'])
        self.assertIn('OS-PORTGROUP', arrayInfo[0]['PortGroup'])
        bExists = os.path.exists(file_name)
        if bExists:
            os.remove(file_name)

    def test_intervals_and_retries_override(
            self):
        file_name = (
            self.create_fake_config_file_no_fast_with_interval_retries())
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        pool = 'gold+1234567891011'
        arrayInfo = self.driver.utils.parse_file_to_get_array_map(
            self.config_file_path)
        poolRec = self.driver.utils.extract_record(arrayInfo, pool)
        extraSpecs = self.driver.common._set_v2_extra_specs(extraSpecs,
                                                            poolRec)
        self.assertEqual(40,
                         self.driver.utils._get_max_job_retries(extraSpecs))
        self.assertEqual(5,
                         self.driver.utils._get_interval_in_secs(extraSpecs))

        bExists = os.path.exists(file_name)
        if bExists:
            os.remove(file_name)

    def test_intervals_and_retries_default(self):
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        pool = 'gold+1234567891011'
        arrayInfo = self.driver.utils.parse_file_to_get_array_map(
            self.config_file_path)
        poolRec = self.driver.utils.extract_record(arrayInfo, pool)
        extraSpecs = self.driver.common._set_v2_extra_specs(extraSpecs,
                                                            poolRec)
        # Set JOB_RETRIES and INTERVAL_10_SEC to 0 to avoid timeout
        self.assertEqual(0,
                         self.driver.utils._get_max_job_retries(extraSpecs))
        self.assertEqual(0,
                         self.driver.utils._get_interval_in_secs(extraSpecs))

    def test_interval_only(self):
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        file_name = self.create_fake_config_file_no_fast_with_interval()
        pool = 'gold+1234567891011'
        arrayInfo = self.driver.utils.parse_file_to_get_array_map(
            self.config_file_path)
        poolRec = self.driver.utils.extract_record(arrayInfo, pool)
        extraSpecs = self.driver.common._set_v2_extra_specs(extraSpecs,
                                                            poolRec)
        # Set JOB_RETRIES 0 to avoid timeout
        self.assertEqual(0,
                         self.driver.utils._get_max_job_retries(extraSpecs))
        self.assertEqual(20,
                         self.driver.utils._get_interval_in_secs(extraSpecs))

        bExists = os.path.exists(file_name)
        if bExists:
            os.remove(file_name)

    def test_retries_only(self):
        extraSpecs = {'volume_backend_name': 'ISCSINoFAST'}
        file_name = self.create_fake_config_file_no_fast_with_retries()
        pool = 'gold+1234567891011'
        arrayInfo = self.driver.utils.parse_file_to_get_array_map(
            self.config_file_path)
        poolRec = self.driver.utils.extract_record(arrayInfo, pool)
        extraSpecs = self.driver.common._set_v2_extra_specs(extraSpecs,
                                                            poolRec)
        self.assertEqual(70,
                         self.driver.utils._get_max_job_retries(extraSpecs))
        # Set INTERVAL_10_SEC to 0 to avoid timeout
        self.assertEqual(0,
                         self.driver.utils._get_interval_in_secs(extraSpecs))

        bExists = os.path.exists(file_name)
        if bExists:
            os.remove(file_name)

    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=2.0)
    @mock.patch.object(
        utils.VMAXUtils,
        'isArrayV3',
        return_value=False)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_pool_capacities',
        return_value=(1234, 1200, 1200, 1))
    @mock.patch.object(
        fast.VMAXFast,
        'is_tiering_policy_enabled',
        return_value=False)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storageSystem',
        return_value=None)
    def test_get_volume_stats_no_fast(self,
                                      mock_storage_system,
                                      mock_is_fast_enabled,
                                      mock_capacity,
                                      mock_is_v3,
                                      mock_or):
        self.driver.common.pool_info['arrays_info'] = (
            [{'EcomServerIp': '1.1.1.1',
              'EcomServerPort': '5989',
              'EcomUserName': 'name',
              'EcomPassword': 'password',
              'SerialNumber': '1234567890',
              'PoolName': 'v2_pool',
              'FastPolicy': 'gold'}])
        self.driver.get_volume_stats(True)
        self.driver.common.pool_info['arrays_info'] = []

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_volume_no_fast_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'storagetype: stripedmetacount': '4',
                      'volume_backend_name': 'ISCSINoFAST'})
    def test_create_volume_no_fast_striped_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_volume_in_CG_no_fast_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.create_volume(self.data.test_volume_CG)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_delete_volume_no_fast_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.delete_volume(self.data.test_volume)

    def test_create_volume_no_fast_failed(self):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume,
                          self.data.test_failed_volume)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_delete_volume_no_fast_notfound(self, _mock_volume_type):
        notfound_delete_vol = {}
        notfound_delete_vol['name'] = 'notfound_delete_vol'
        notfound_delete_vol['id'] = '10'
        notfound_delete_vol['CreationClassName'] = 'Symmm_StorageVolume'
        notfound_delete_vol['SystemName'] = self.data.storage_system
        notfound_delete_vol['DeviceID'] = notfound_delete_vol['id']
        notfound_delete_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        notfound_delete_vol['volume_type_id'] = 'abc'
        notfound_delete_vol['provider_location'] = None
        notfound_delete_vol['host'] = self.data.fake_host
        name = {}
        name['classname'] = 'Symm_StorageVolume'
        keys = {}
        keys['CreationClassName'] = notfound_delete_vol['CreationClassName']
        keys['SystemName'] = notfound_delete_vol['SystemName']
        keys['DeviceID'] = notfound_delete_vol['DeviceID']
        keys['SystemCreationClassName'] = (
            notfound_delete_vol['SystemCreationClassName'])
        name['keybindings'] = keys

        self.driver.delete_volume(notfound_delete_vol)

    @mock.patch.object(
        utils.VMAXUtils,
        'wait_for_job_complete',
        return_value=(-1, 'error'))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_delete_volume_failed(
            self, _mock_volume_type, mock_storage_system, mock_wait):
        self.driver.create_volume(self.data.failed_delete_vol)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.delete_volume,
                          self.data.failed_delete_vol)

    @mock.patch.object(
        common.VMAXCommon,
        '_is_same_host',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'hostlunid': 1,
                      'storagesystem': VMAXCommonData.storage_system},
                      False, {}))
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_already_mapped_no_fast_success(
            self, _mock_volume_type, mock_wrap_group, mock_wrap_device,
            mock_is_same_host):
        self.driver.common._get_correct_port_group = mock.Mock(
            return_value=self.data.port_group)
        self.driver.initialize_connection(self.data.test_volume,
                                          self.data.connector)

    @mock.patch.object(
        masking.VMAXMasking,
        '_check_adding_volume_to_storage_group',
        return_value=None)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storage_masking_group',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_map_new_masking_view_no_fast_success(
            self, _mock_volume_type, mock_wrap_group,
            mock_storage_group, mock_add_volume):
        self.driver.common._wrap_find_device_number = mock.Mock(
            return_value=({}, False, {}))
        self.driver.initialize_connection(self.data.test_volume,
                                          self.data.connector)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_port_group_from_source',
        return_value={'CreationClassName': 'CIM_TargetMaskingGroup',
                      'ElementName': 'OS-portgroup-PG'})
    @mock.patch.object(
        common.VMAXCommon,
        '_get_storage_group_from_source',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        common.VMAXCommon,
        '_is_same_host',
        return_value=False)
    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'hostlunid': 1,
                      'storagesystem': VMAXCommonData.storage_system},
                      True,
                      {'hostlunid': 1,
                      'storagesystem': VMAXCommonData.storage_system}))
    @mock.patch.object(
        common.VMAXCommon,
        '_wrap_find_device_number',
        return_value=({}, True,
                      {'hostlunid': 1,
                      'storagesystem': VMAXCommonData.storage_system}))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_map_live_migration_no_fast_success(self,
                                                _mock_volume_type,
                                                mock_wrap_device,
                                                mock_device,
                                                mock_same_host,
                                                mock_sg_from_mv,
                                                mock_pg_from_mv):
        extraSpecs = self.data.extra_specs
        rollback_dict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        with mock.patch.object(self.driver.common.masking,
                               'setup_masking_view',
                               return_value=rollback_dict):
            self.driver.initialize_connection(self.data.test_volume,
                                              self.data.connector)

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_initiator_group_from_masking_view',
        return_value='value')
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_initiator_masking_group',
        return_value='value')
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_masking_view',
        return_value='value')
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_map_existing_masking_view_no_fast_success(
            self, _mock_volume_type, mock_wrap_group, mock_storage_group,
            mock_initiator_group, mock_ig_from_mv):
        self.driver.initialize_connection(self.data.test_volume,
                                          self.data.connector)

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'storagesystem': VMAXCommonData.storage_system},
                      False, {}))
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    def test_map_no_fast_failed(self, mock_wrap_group, mock_wrap_device):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.initialize_connection,
                          self.data.test_volume,
                          self.data.connector)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_initiator_group_from_masking_view',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_initiator_masking_group',
        return_value='myInitGroup')
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storage_masking_group',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_detach_no_fast_success(
            self, mock_volume_type, mock_storage_group,
            mock_ig, mock_igc):
        self.driver.terminate_connection(
            self.data.test_volume, self.data.connector)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_size',
        return_value='2147483648')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_extend_volume_no_fast_success(
            self, _mock_volume_type, mock_volume_size):
        newSize = '2'
        self.driver.extend_volume(self.data.test_volume, newSize)

    @mock.patch.object(
        utils.VMAXUtils,
        'check_if_volume_is_extendable',
        return_value='False')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'storagetype: stripedmetacount': '4',
                      'volume_backend_name': 'ISCSINoFAST'})
    def test_extend_volume_striped_no_fast_failed(
            self, _mock_volume_type, _mock_is_extendable):
        newSize = '2'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.extend_volume,
                          self.data.test_volume,
                          newSize)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_snapshot_different_sizes_meta_no_fast_success(
            self, mock_volume_type,
            mock_meta, mock_size, mock_pool):
        common = self.driver.common
        volumeDict = {'classname': u'Symm_StorageVolume',
                      'keybindings': VMAXCommonData.keybindings}
        common.provision.create_volume_from_pool = (
            mock.Mock(return_value=(volumeDict, 0)))
        common.provision.get_volume_dict_from_job = (
            mock.Mock(return_value=volumeDict))
        self.driver.create_snapshot(self.data.test_snapshot)

    @mock.patch.object(
        utils.VMAXUtils,
        'parse_file_to_get_array_map',
        return_value=None)
    def test_create_snapshot_no_fast_failed(self, mock_pool):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_snapshot,
                          self.data.test_snapshot)

    @unittest.skip("Skip until bug #1578986 is fixed")
    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_volume_from_same_size_meta_snapshot(
            self, mock_volume_type, mock_sync_sv, mock_meta, mock_size,
            mock_compare):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.driver.create_volume_from_snapshot(
            self.data.test_volume, self.data.test_volume)

    def test_create_volume_from_snapshot_no_fast_failed(self):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume_from_snapshot,
                          self.data.test_volume,
                          self.data.test_volume)

    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_find_storage_sync_sv_sv',
        return_value=(None, None))
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_clone_simple_volume_no_fast_success(
            self, mock_volume_type, mock_volume, mock_sync_sv,
            mock_simple_volume, mock_compare):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.driver.create_cloned_volume(self.data.test_volume,
                                         VMAXCommonData.test_source_volume)

    # Bug https://bugs.launchpad.net/cinder/+bug/1440154
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    @mock.patch.object(
        provision.VMAXProvision,
        'create_element_replica')
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    def test_create_clone_assert_clean_up_target_volume(
            self, mock_sync, mock_create_replica, mock_volume_type,
            mock_volume, mock_capacities, mock_pool, mock_meta_volume):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        e = exception.VolumeBackendAPIException('CreateElementReplica Ex')
        common = self.driver.common
        common._delete_from_pool = mock.Mock(return_value=0)
        conn = self.fake_ecom_connection()
        storageConfigService = (
            common.utils.find_storage_configuration_service(
                conn, self.data.storage_system))
        mock_create_replica.side_effect = e
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_cloned_volume,
                          self.data.test_volume,
                          VMAXCommonData.test_source_volume)
        extraSpecs = common._initial_setup(self.data.test_volume)
        fastPolicy = extraSpecs['storagetype:fastpolicy']
        targetInstance = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        common._delete_from_pool.assert_called_with(storageConfigService,
                                                    targetInstance,
                                                    targetInstance['Name'],
                                                    targetInstance['DeviceID'],
                                                    fastPolicy,
                                                    extraSpecs)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_migrate_volume_no_fast_success(self, _mock_volume_type):
        self.driver.migrate_volume(self.data.test_ctxt, self.data.test_volume,
                                   self.data.test_host)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.create_consistencygroup(
            self.data.test_ctxt, self.data.test_CG)

    @mock.patch.object(
        FakeDB,
        'volume_get_all_by_group',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_delete_CG_no_volumes_no_fast_success(
            self, _mock_volume_type, _mock_storage_system,
            _mock_db_volumes):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_delete_CG_with_volumes_no_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        utils.VMAXUtils,
        'find_group_sync_rg_by_target',
        return_value="")
    @mock.patch.object(
        common.VMAXCommon,
        '_get_members_of_replication_group',
        return_value=())
    @mock.patch.object(
        common.VMAXCommon,
        '_find_consistency_group',
        return_value=(
            VMAXCommonData.test_CG,
            VMAXCommonData.test_CG['name'] + "_" + (
                VMAXCommonData.test_CG['id'])))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage, _mock_cg, _mock_members,
            _mock_rg):
        self.driver.create_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_delete_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage):
        self.driver.delete_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_update_CG_add_volume_no_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        add_volumes = []
        add_volumes.append(self.data.test_source_volume)
        remove_volumes = None
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Multiple volumes
        add_volumes.append(self.data.test_source_volume)
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Can't find CG
        self.driver.common._find_consistency_group = mock.Mock(
            return_value=(None, 'cg_name'))
        self.assertRaises(exception.ConsistencyGroupNotFound,
                          self.driver.update_consistencygroup,
                          self.data.test_ctxt, self.data.test_CG,
                          add_volumes, remove_volumes)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_update_CG_remove_volume_no_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        remove_volumes = []
        remove_volumes.append(self.data.test_source_volume)
        add_volumes = None
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Multiple volumes
        remove_volumes.append(self.data.test_source_volume)
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)

    # Bug https://bugs.launchpad.net/cinder/+bug/1442376
    @unittest.skip("Skip until bug #1578986 is fixed")
    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def _test_create_clone_with_different_meta_sizes(
            self, mock_volume_type, mock_volume,
            mock_meta, mock_size, mock_pool, mock_compare):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        common = self.driver.common
        volumeDict = {'classname': u'Symm_StorageVolume',
                      'keybindings': VMAXCommonData.keybindings}
        volume = {'size': 0}
        common.provision.create_volume_from_pool = (
            mock.Mock(return_value=(volumeDict, volume['size'])))
        common.provision.get_volume_dict_from_job = (
            mock.Mock(return_value=volumeDict))

        common._create_composite_volume = (
            mock.Mock(return_value=(0,
                                    volumeDict,
                                    VMAXCommonData.storage_system)))
        self.driver.create_cloned_volume(self.data.test_volume,
                                         VMAXCommonData.test_source_volume)
        extraSpecs = self.driver.common._initial_setup(self.data.test_volume)
        common._create_composite_volume.assert_called_with(
            volume, "TargetBaseVol", 1234567, extraSpecs, 1)

    def test_get_volume_element_name(self):
        volumeId = 'ea95aa39-080b-4f11-9856-a03acf9112ad'
        util = self.driver.common.utils
        volumeElementName = util.get_volume_element_name(volumeId)
        expectVolumeElementName = (
            utils.VOLUME_ELEMENT_NAME_PREFIX + volumeId)
        self.assertEqual(expectVolumeElementName, volumeElementName)

    def test_get_associated_replication_from_source_volume(self):
        conn = self.fake_ecom_connection()
        utils = self.driver.common.utils
        repInstanceName = (
            utils.get_associated_replication_from_source_volume(
                conn, self.data.storage_system,
                self.data.test_volume['device_id']))
        expectInstanceName = (
            conn.EnumerateInstanceNames('SE_StorageSynchronized_SV_SV')[0])
        self.assertEqual(expectInstanceName, repInstanceName)

    def test_get_array_and_device_id_success(self):
        deviceId = '0123'
        arrayId = '1234567891011'
        external_ref = {u'source-name': deviceId}
        volume = {'volume_metadata': [{'key': 'array', 'value': arrayId}]
                  }
        volume['host'] = 'HostX@Backend#Bronze+SRP_1+1234567891011'
        utils = self.driver.common.utils
        (arrId, devId) = utils.get_array_and_device_id(volume, external_ref)
        self.assertEqual(arrayId, arrId)
        self.assertEqual(deviceId, devId)

    def test_get_array_and_device_id_failed(self):
        deviceId = '0123'
        arrayId = '1234567891011'
        external_ref = {u'no-source-name': deviceId}
        volume = {'volume_metadata': [{'key': 'array', 'value': arrayId}]
                  }
        volume['host'] = 'HostX@Backend#Bronze+SRP_1+1234567891011'
        utils = self.driver.common.utils
        self.assertRaises(exception.VolumeBackendAPIException,
                          utils.get_array_and_device_id,
                          volume,
                          external_ref)

    def test_rename_volume(self):
        conn = self.fake_ecom_connection()
        util = self.driver.common.utils
        newName = 'new_name'
        volume = {}
        volume['CreationClassName'] = 'Symm_StorageVolume'
        volume['DeviceID'] = '1'
        volume['ElementName'] = 'original_name'
        pywbem = mock.Mock()
        pywbem.cim_obj = mock.Mock()
        pywbem.cim_obj.CIMInstance = mock.Mock()
        utils.pywbem = pywbem
        volumeInstance = conn.GetInstance(volume)
        originalName = volumeInstance['ElementName']
        volumeInstance = util.rename_volume(conn, volumeInstance, newName)
        self.assertEqual(newName, volumeInstance['ElementName'])
        volumeInstance = util.rename_volume(
            conn, volumeInstance, originalName)
        self.assertEqual(originalName, volumeInstance['ElementName'])

    def test_get_smi_version(self):
        conn = self.fake_ecom_connection()
        utils = self.driver.common.utils
        version = utils.get_smi_version(conn)
        expected = int(str(self.data.majorVersion)
                       + str(self.data.minorVersion)
                       + str(self.data.revNumber))
        self.assertEqual(version, expected)

    def test_get_pool_name(self):
        conn = self.fake_ecom_connection()
        utils = self.driver.common.utils
        poolInstanceName = {}
        poolInstanceName['InstanceID'] = "SATA_GOLD1"
        poolInstanceName['CreationClassName'] = 'Symm_VirtualProvisioningPool'
        poolName = utils.get_pool_name(conn, poolInstanceName)
        self.assertEqual(poolName, self.data.poolname)

    def test_get_meta_members_capacity_in_byte(self):
        conn = self.fake_ecom_connection()
        utils = self.driver.common.utils
        memberVolumeInstanceNames = []
        volumeHead = EMC_StorageVolume()
        volumeHead.classname = 'Symm_StorageVolume'
        blockSize = self.data.block_size
        volumeHead['ConsumableBlocks'] = (
            self.data.metaHead_volume['ConsumableBlocks'])
        volumeHead['BlockSize'] = blockSize
        volumeHead['DeviceID'] = self.data.metaHead_volume['DeviceID']
        memberVolumeInstanceNames.append(volumeHead)
        metaMember1 = EMC_StorageVolume()
        metaMember1.classname = 'Symm_StorageVolume'
        metaMember1['ConsumableBlocks'] = (
            self.data.meta_volume1['ConsumableBlocks'])
        metaMember1['BlockSize'] = blockSize
        metaMember1['DeviceID'] = self.data.meta_volume1['DeviceID']
        memberVolumeInstanceNames.append(metaMember1)
        metaMember2 = EMC_StorageVolume()
        metaMember2.classname = 'Symm_StorageVolume'
        metaMember2['ConsumableBlocks'] = (
            self.data.meta_volume2['ConsumableBlocks'])
        metaMember2['BlockSize'] = blockSize
        metaMember2['DeviceID'] = self.data.meta_volume2['DeviceID']
        memberVolumeInstanceNames.append(metaMember2)
        capacities = utils.get_meta_members_capacity_in_byte(
            conn, memberVolumeInstanceNames)
        headSize = (
            volumeHead['ConsumableBlocks'] -
            metaMember1['ConsumableBlocks'] -
            metaMember2['ConsumableBlocks'])
        expected = [headSize * blockSize,
                    metaMember1['ConsumableBlocks'] * blockSize,
                    metaMember2['ConsumableBlocks'] * blockSize]
        self.assertEqual(capacities, expected)

    def test_get_composite_elements(self):
        conn = self.fake_ecom_connection()
        utils = self.driver.common.utils
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        memberVolumeInstanceNames = utils.get_composite_elements(
            conn, volumeInstance)
        expected = [self.data.metaHead_volume,
                    self.data.meta_volume1,
                    self.data.meta_volume2]
        self.assertEqual(memberVolumeInstanceNames, expected)

    def test_get_volume_model_updates(self):
        utils = self.driver.common.utils
        status = 'status-string'
        volumes = utils.get_volume_model_updates(
            self.driver.db.volume_get_all_by_group("", 5),
            self.data.test_CG['id'],
            status)
        self.assertEqual(status, volumes[0]['status'])

    @mock.patch.object(
        utils.VMAXUtils,
        'find_group_sync_rg_by_target',
        return_value="")
    @mock.patch.object(
        common.VMAXCommon,
        '_find_consistency_group',
        return_value=(
            VMAXCommonData.source_CG,
            VMAXCommonData.source_CG['name'] + "_" + (
                VMAXCommonData.source_CG['id'])))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    def test_create_consistencygroup_from_src(
            self, _mock_volume_type, _mock_storage, _mock_cg, _mock_rg):
        volumes = []
        volumes.append(self.data.test_source_volume)
        snapshots = []
        self.data.test_snapshot['volume_size'] = "10"
        snapshots.append(self.data.test_snapshot)
        model_update, volumes_model_update = (
            self.driver.create_consistencygroup_from_src(
                self.data.test_ctxt, self.data.source_CG, volumes,
                self.data.test_CG_snapshot, snapshots))
        self.assertEqual({'status': fields.ConsistencyGroupStatus.AVAILABLE},
                         model_update)
        for volume_model_update in volumes_model_update:
            if 'status' in volume_model_update:
                self.assertEqual(volume_model_update['status'], 'available')
            if 'id' in volume_model_update:
                self.assertEqual(volume_model_update['id'], '2')
            self.assertTrue('provider_location' in volume_model_update)
            self.assertTrue('admin_metadata' in volume_model_update)

    @mock.patch.object(
        common.VMAXCommon,
        '_update_pool_stats',
        return_value={1, 2, 3, 4, 5})
    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=1.0)
    def test_ssl_support(self, mock_ratio, pool_stats):
        self.driver.common.pool_info['arrays_info'] = (
            [{'EcomServerIp': '1.1.1.1',
              'EcomServerPort': '5989',
              'EcomUserName': 'name',
              'EcomPassword': 'password',
              'SerialNumber': '1234567890',
              'PoolName': 'v2_pool'}])
        self.driver.common.update_volume_stats()
        self.assertTrue(self.driver.common.ecomUseSSL)

    def _cleanup(self):
        if self.config_file_path:
            bExists = os.path.exists(self.config_file_path)
            if bExists:
                os.remove(self.config_file_path)
        shutil.rmtree(self.tempdir)


class VMAXISCSIDriverFastTestCase(test.TestCase):

    def setUp(self):

        self.data = VMAXCommonData()

        self.tempdir = tempfile.mkdtemp()
        super(VMAXISCSIDriverFastTestCase, self).setUp()
        self.config_file_path = None
        self.create_fake_config_file_fast()
        self.addCleanup(self._cleanup)

        configuration = mock.Mock()
        configuration.cinder_emc_config_file = self.config_file_path
        configuration.safe_get.return_value = 'ISCSIFAST'
        configuration.config_group = 'ISCSIFAST'
        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         self.fake_is_v3)
        self.mock_object(cinder_utils, 'get_bool_param',
                         return_value=False)
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.patcher = mock.patch(
            'oslo_service.loopingcall.FixedIntervalLoopingCall',
            new=unit_utils.ZeroIntervalLoopingCall)
        self.patcher.start()

    def create_fake_config_file_fast(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        fastPolicy = doc.createElement("FastPolicy")
        fastPolicyText = doc.createTextNode("GOLD1")
        emc.appendChild(fastPolicy)
        fastPolicy.appendChild(fastPolicyText)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("gold")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        filename = 'cinder_emc_config_ISCSIFAST.xml'

        self.config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()

    def fake_ecom_connection(self):
        conn = FakeEcomConnection()
        return conn

    def fake_is_v3(self, conn, serialNumber):
        return False

    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=2.0)
    @mock.patch.object(
        fast.VMAXFast,
        'get_capacities_associated_to_policy',
        return_value=(1234, 1200, 1200, 1))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_pool_capacities',
        return_value=(1234, 1200, 1200, 1))
    @mock.patch.object(
        fast.VMAXFast,
        'get_tier_policy_by_name',
        return_value=None)
    @mock.patch.object(
        fast.VMAXFast,
        'is_tiering_policy_enabled',
        return_value=True)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storageSystem',
        return_value=None)
    def test_get_volume_stats_fast(self,
                                   mock_storage_system,
                                   mock_is_fast_enabled,
                                   mock_get_policy,
                                   mock_pool_capacities,
                                   mock_capacities_associated_to_policy,
                                   mock_or):
        self.driver.common.pool_info['arrays_info'] = (
            [{'EcomServerIp': '1.1.1.1',
              'EcomServerPort': '5989',
              'EcomUserName': 'name',
              'EcomPassword': 'password',
              'SerialNumber': '1234567890',
              'PoolName': 'v2_pool',
              'FastPolicy': 'gold'}])
        self.driver.get_volume_stats(True)
        self.driver.common.pool_info['arrays_info'] = []

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_volume_fast_success(
            self, _mock_volume_type, mock_storage_system, mock_pool_policy):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'storagetype: stripedmetacount': '4',
                      'volume_backend_name': 'ISCSIFAST'})
    def test_create_volume_fast_striped_success(
            self, _mock_volume_type, mock_storage_system, mock_pool_policy):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_volume_in_CG_fast_success(
            self, _mock_volume_type, mock_storage_system, mock_pool_policy):
        self.driver.create_volume(self.data.test_volume_CG)

    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_delete_volume_fast_success(
            self, _mock_volume_type, mock_storage_group):
        self.driver.delete_volume(self.data.test_volume)

    def test_create_volume_fast_failed(self):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume,
                          self.data.test_failed_volume)

    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_delete_volume_fast_notfound(
            self, _mock_volume_type, mock_wrapper):
        notfound_delete_vol = {}
        notfound_delete_vol['name'] = 'notfound_delete_vol'
        notfound_delete_vol['id'] = '10'
        notfound_delete_vol['CreationClassName'] = 'Symmm_StorageVolume'
        notfound_delete_vol['SystemName'] = self.data.storage_system
        notfound_delete_vol['DeviceID'] = notfound_delete_vol['id']
        notfound_delete_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        notfound_delete_vol['host'] = self.data.fake_host
        name = {}
        name['classname'] = 'Symm_StorageVolume'
        keys = {}
        keys['CreationClassName'] = notfound_delete_vol['CreationClassName']
        keys['SystemName'] = notfound_delete_vol['SystemName']
        keys['DeviceID'] = notfound_delete_vol['DeviceID']
        keys['SystemCreationClassName'] = (
            notfound_delete_vol['SystemCreationClassName'])
        name['keybindings'] = keys
        notfound_delete_vol['volume_type_id'] = 'abc'
        notfound_delete_vol['provider_location'] = None
        self.driver.delete_volume(notfound_delete_vol)

    @mock.patch.object(
        utils.VMAXUtils,
        'wait_for_job_complete',
        return_value=(-1, 'error'))
    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_delete_volume_fast_failed(
            self, _mock_volume_type, _mock_storage_group,
            mock_storage_system, mock_policy_pool, mock_wait):
        self.driver.create_volume(self.data.failed_delete_vol)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.delete_volume,
                          self.data.failed_delete_vol)

    @mock.patch.object(
        common.VMAXCommon,
        '_is_same_host',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'hostlunid': 1,
                      'storagesystem': VMAXCommonData.storage_system},
                      False, {}))
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_already_mapped_fast_success(
            self, _mock_volume_type, mock_wrap_group, mock_wrap_device,
            mock_is_same_host):
        self.driver.common._get_correct_port_group = mock.Mock(
            return_value=self.data.port_group)
        self.driver.initialize_connection(self.data.test_volume,
                                          self.data.connector)

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'storagesystem': VMAXCommonData.storage_system},
                      False, {}))
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    def test_map_fast_failed(self, mock_wrap_group, mock_wrap_device):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.initialize_connection,
                          self.data.test_volume,
                          self.data.connector)

    @mock.patch.object(
        common.VMAXCommon,
        'get_target_wwns_from_masking_view',
        return_value=[{'Name': '5000090000000000'}])
    @mock.patch.object(
        masking.VMAXMasking,
        'get_initiator_group_from_masking_view',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_initiator_masking_group',
        return_value='myInitGroup')
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storage_masking_group',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_detach_fast_success(
            self, mock_volume_type, mock_storage_group,
            mock_ig, mock_igc, mock_tw):
        self.driver.terminate_connection(
            self.data.test_volume, self.data.connector)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_size',
        return_value='2147483648')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_extend_volume_fast_success(
            self, _mock_volume_type, mock_volume_size):
        newSize = '2'
        self.driver.extend_volume(self.data.test_volume, newSize)

    @mock.patch.object(
        utils.VMAXUtils,
        'check_if_volume_is_extendable',
        return_value='False')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_extend_volume_striped_fast_failed(
            self, _mock_volume_type, _mock_is_extendable):
        newSize = '2'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.extend_volume,
                          self.data.test_volume,
                          newSize)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_snapshot_different_sizes_meta_fast_success(
            self, mock_volume_type,
            mock_meta, mock_size, mock_pool, mock_policy):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        common = self.driver.common

        volumeDict = {'classname': u'Symm_StorageVolume',
                      'keybindings': VMAXCommonData.keybindings}
        common.provision.create_volume_from_pool = (
            mock.Mock(return_value=(volumeDict, 0)))
        common.provision.get_volume_dict_from_job = (
            mock.Mock(return_value=volumeDict))
        common.fast.is_volume_in_default_SG = (
            mock.Mock(return_value=True))
        self.driver.create_snapshot(self.data.test_snapshot)

    @mock.patch.object(
        utils.VMAXUtils,
        'parse_file_to_get_array_map',
        return_value=None)
    def test_create_snapshot_fast_failed(self, mock_pool):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_snapshot,
                          self.data.test_snapshot)

    @unittest.skip("Skip until bug #1578986 is fixed")
    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        utils.VMAXUtils,
        'wait_for_job_complete',
        return_value=(0, 'success'))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_volume_from_same_size_meta_snapshot(
            self, mock_volume_type, mock_sync_sv, mock_meta, mock_size,
            mock_wait, mock_compare):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        common = self.driver.common
        common.fast.is_volume_in_default_SG = mock.Mock(return_value=True)
        self.driver.create_volume_from_snapshot(
            self.data.test_volume, self.data.test_volume)

    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=False)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    @mock.patch.object(
        utils.VMAXUtils,
        'find_replication_service',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_create_volume_from_snapshot_fast_failed(
            self, mock_volume_type,
            mock_rep_service, mock_sync_sv, mock_license):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume_from_snapshot,
                          self.data.test_volume,
                          VMAXCommonData.test_source_volume)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_clone_fast_failed(
            self, mock_volume_type, mock_vol,
            mock_policy, mock_meta, mock_size, mock_pool):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.driver.common._modify_and_get_composite_volume_instance = (
            mock.Mock(return_value=(1, None)))
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_cloned_volume,
                          self.data.test_volume,
                          VMAXCommonData.test_source_volume)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_migrate_volume_fast_success(self, _mock_volume_type):
        self.driver.migrate_volume(self.data.test_ctxt, self.data.test_volume,
                                   self.data.test_host)

    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        utils.VMAXUtils,
        'parse_pool_instance_id',
        return_value=('silver', 'SYMMETRIX+000195900551'))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_retype_volume_fast_success(
            self, _mock_volume_type, mock_values, mock_wrap):
        self.driver.retype(
            self.data.test_ctxt, self.data.test_volume, self.data.new_type,
            self.data.diff, self.data.test_host)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_CG_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.create_consistencygroup(
            self.data.test_ctxt, self.data.test_CG)

    @mock.patch.object(
        FakeDB,
        'volume_get_all_by_group',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_delete_CG_no_volumes_fast_success(
            self, _mock_volume_type, _mock_storage_system,
            _mock_db_volumes):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_delete_CG_with_volumes_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        utils.VMAXUtils,
        'find_group_sync_rg_by_target',
        return_value="")
    @mock.patch.object(
        common.VMAXCommon,
        '_get_members_of_replication_group',
        return_value=())
    @mock.patch.object(
        common.VMAXCommon,
        '_find_consistency_group',
        return_value=(
            VMAXCommonData.test_CG,
            VMAXCommonData.test_CG['name'] + "_" + (
                VMAXCommonData.test_CG['id'])))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_create_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage, _mock_cg, _mock_members,
            _mock_rg):
        self.driver.create_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_delete_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage):
        self.driver.delete_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_update_CG_add_volume_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        add_volumes = []
        add_volumes.append(self.data.test_source_volume)
        remove_volumes = None
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Multiple volumes
        add_volumes.append(self.data.test_source_volume)
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSIFAST'})
    def test_update_CG_remove_volume_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        remove_volumes = []
        remove_volumes.append(self.data.test_source_volume)
        add_volumes = None
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Multiple volumes
        remove_volumes.append(self.data.test_source_volume)
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)

    def _cleanup(self):
        bExists = os.path.exists(self.config_file_path)
        if bExists:
            os.remove(self.config_file_path)
        shutil.rmtree(self.tempdir)


@ddt.ddt
class VMAXFCDriverNoFastTestCase(test.TestCase):
    def setUp(self):

        self.data = VMAXCommonData()

        self.tempdir = tempfile.mkdtemp()
        super(VMAXFCDriverNoFastTestCase, self).setUp()
        self.config_file_path = None
        self.create_fake_config_file_no_fast()
        self.addCleanup(self._cleanup)

        configuration = mock.Mock()
        configuration.cinder_emc_config_file = self.config_file_path
        configuration.safe_get.return_value = 'FCNoFAST'
        configuration.config_group = 'FCNoFAST'

        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         self.fake_is_v3)
        self.mock_object(utils.VMAXUtils, '_is_sync_complete',
                         return_value=True)
        self.mock_object(cinder_utils, 'get_bool_param',
                         return_value=False)
        driver = fc.VMAXFCDriver(configuration=configuration)
        driver.db = FakeDB()
        driver.common.conn = FakeEcomConnection()
        driver.zonemanager_lookup_service = FakeLookupService()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    def create_fake_config_file_no_fast(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("gold")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        filename = 'cinder_emc_config_FCNoFAST.xml'

        self.config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()

    def fake_ecom_connection(self):
        conn = FakeEcomConnection()
        return conn

    def fake_is_v3(self, conn, serialNumber):
        return False

    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=2.0)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_pool_capacities',
        return_value=(1234, 1200, 1200, 1))
    @mock.patch.object(
        fast.VMAXFast,
        'is_tiering_policy_enabled',
        return_value=False)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storageSystem',
        return_value=None)
    def test_get_volume_stats_no_fast(self,
                                      mock_storage_system,
                                      mock_is_fast_enabled,
                                      mock_capacity,
                                      mock_or):
        self.driver.get_volume_stats(True)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_create_volume_no_fast_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'storagetype: stripedmetacount': '4',
                      'volume_backend_name': 'FCNoFAST'})
    def test_create_volume_no_fast_striped_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_create_volume_in_CG_no_fast_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.create_volume(self.data.test_volume_CG)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_delete_volume_no_fast_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.delete_volume(self.data.test_volume)

    def test_create_volume_no_fast_failed(self):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume,
                          self.data.test_failed_volume)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_delete_volume_no_fast_notfound(self, _mock_volume_type):
        notfound_delete_vol = {}
        notfound_delete_vol['name'] = 'notfound_delete_vol'
        notfound_delete_vol['id'] = '10'
        notfound_delete_vol['CreationClassName'] = 'Symmm_StorageVolume'
        notfound_delete_vol['SystemName'] = self.data.storage_system
        notfound_delete_vol['DeviceID'] = notfound_delete_vol['id']
        notfound_delete_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        notfound_delete_vol['host'] = self.data.fake_host
        name = {}
        name['classname'] = 'Symm_StorageVolume'
        keys = {}
        keys['CreationClassName'] = notfound_delete_vol['CreationClassName']
        keys['SystemName'] = notfound_delete_vol['SystemName']
        keys['DeviceID'] = notfound_delete_vol['DeviceID']
        keys['SystemCreationClassName'] = (
            notfound_delete_vol['SystemCreationClassName'])
        name['keybindings'] = keys
        notfound_delete_vol['volume_type_id'] = 'abc'
        notfound_delete_vol['provider_location'] = None
        self.driver.delete_volume(notfound_delete_vol)

    @mock.patch.object(
        utils.VMAXUtils,
        'wait_for_job_complete',
        return_value=(-1, 'error'))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_delete_volume_failed(
            self, _mock_volume_type, mock_storage_system, mock_wait):
        self.driver.create_volume(self.data.failed_delete_vol)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.delete_volume,
                          self.data.failed_delete_vol)

    @mock.patch.object(
        common.VMAXCommon,
        '_is_same_host',
        return_value=True)
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=VMAXCommonData.lunmaskctrl_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_map_lookup_service_no_fast_success(
            self, _mock_volume_type, mock_maskingview, mock_is_same_host):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        common = self.driver.common
        common.get_target_wwns_from_masking_view = mock.Mock(
            return_value=VMAXCommonData.target_wwns)
        common._get_correct_port_group = mock.Mock(
            return_value=self.data.port_group)
        lookup_service = self.driver.zonemanager_lookup_service
        lookup_service.get_device_mapping_from_network = mock.Mock(
            return_value=VMAXCommonData.device_map)
        data = self.driver.initialize_connection(self.data.test_volume,
                                                 self.data.connector)
        common.get_target_wwns_from_masking_view.assert_called_once_with(
            VMAXCommonData.storage_system, self.data.test_volume,
            VMAXCommonData.connector)
        lookup_service.get_device_mapping_from_network.assert_called_once_with(
            VMAXCommonData.connector['wwpns'],
            VMAXCommonData.target_wwns)

        # Test the lookup service code path.
        for init, target in data['data']['initiator_target_map'].items():
            self.assertEqual(init, target[0][::-1])

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'Name': "0001"}, False, {}))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_map_no_fast_failed(self, _mock_volume_type, mock_wrap_device):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.initialize_connection,
                          self.data.test_volume,
                          self.data.connector)

    @mock.patch.object(
        common.VMAXCommon,
        'check_ig_instance_name',
        return_value=None)
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_initiator_masking_group',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_by_volume',
        return_value=VMAXCommonData.lunmaskctrl_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_detach_no_fast_last_volume_success(
            self, mock_volume_type, mock_mv, mock_ig, mock_check_ig):
        # last volume so initiatorGroup will be deleted by terminate connection
        self.driver.terminate_connection(self.data.test_source_volume,
                                         self.data.connector)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_size',
        return_value='2147483648')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_extend_volume_no_fast_success(self, _mock_volume_type,
                                           _mock_volume_size):
        newSize = '2'
        self.driver.extend_volume(self.data.test_volume, newSize)

    @mock.patch.object(
        utils.VMAXUtils,
        'check_if_volume_is_extendable',
        return_value='False')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_extend_volume_striped_no_fast_failed(
            self, _mock_volume_type, _mock_is_extendable):
        newSize = '2'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.extend_volume,
                          self.data.test_volume,
                          newSize)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_migrate_volume_no_fast_success(self, _mock_volume_type):
        self.driver.migrate_volume(self.data.test_ctxt, self.data.test_volume,
                                   self.data.test_host)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_create_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.create_consistencygroup(
            self.data.test_ctxt, self.data.test_CG)

    @mock.patch.object(
        FakeDB,
        'volume_get_all_by_group',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_delete_CG_no_volumes_no_fast_success(
            self, _mock_volume_type, _mock_storage_system,
            _mock_db_volumes):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_delete_CG_with_volumes_no_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        utils.VMAXUtils,
        'find_group_sync_rg_by_target',
        return_value="")
    @mock.patch.object(
        common.VMAXCommon,
        '_get_members_of_replication_group',
        return_value=())
    @mock.patch.object(
        common.VMAXCommon,
        '_find_consistency_group',
        return_value=(
            VMAXCommonData.test_CG,
            VMAXCommonData.test_CG['name'] + "_" + (
                VMAXCommonData.test_CG['id'])))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_create_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage, _mock_cg, _mock_members,
            _mock_rg):
        self.driver.create_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCNoFAST'})
    def test_delete_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage):
        self.driver.delete_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    def test_unmanage_no_fast_success(self):
        keybindings = {'CreationClassName': u'Symm_StorageVolume',
                       'SystemName': u'SYMMETRIX+000195900000',
                       'DeviceID': u'1',
                       'SystemCreationClassName': u'Symm_StorageSystem'}
        provider_location = {'classname': 'Symm_StorageVolume',
                             'keybindings': keybindings}

        volume = {'name': 'vol1',
                  'size': 1,
                  'id': '1',
                  'device_id': '1',
                  'provider_auth': None,
                  'project_id': 'project',
                  'display_name': 'vol1',
                  'display_description': 'test volume',
                  'volume_type_id': 'abc',
                  'provider_location': six.text_type(provider_location),
                  'status': 'available',
                  'host': self.data.fake_host,
                  'NumberOfBlocks': 100,
                  'BlockSize': self.data.block_size
                  }
        common = self.driver.common
        common._initial_setup = mock.Mock(
            return_value={'volume_backend_name': 'FCNoFAST',
                          'storagetype:fastpolicy': None})
        utils = self.driver.common.utils
        utils.rename_volume = mock.Mock(return_value=None)
        self.driver.unmanage(volume)
        utils.rename_volume.assert_called_once_with(
            common.conn, common._find_lun(volume), '1')

    def test_unmanage_no_fast_failed(self):
        keybindings = {'CreationClassName': u'Symm_StorageVolume',
                       'SystemName': u'SYMMETRIX+000195900000',
                       'DeviceID': u'999',
                       'SystemCreationClassName': u'Symm_StorageSystem'}
        provider_location = {'classname': 'Symm_StorageVolume',
                             'keybindings': keybindings}

        volume = {'name': 'NO_SUCH_VOLUME',
                  'size': 1,
                  'id': '999',
                  'device_id': '999',
                  'provider_auth': None,
                  'project_id': 'project',
                  'display_name': 'No such volume',
                  'display_description': 'volume not on the array',
                  'volume_type_id': 'abc',
                  'provider_location': six.text_type(provider_location),
                  'status': 'available',
                  'host': self.data.fake_host,
                  'NumberOfBlocks': 100,
                  'BlockSize': self.data.block_size
                  }
        common = self.driver.common
        common._initial_setup = mock.Mock(
            return_value={'volume_backend_name': 'FCNoFAST',
                          'fastpolicy': None})
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.unmanage,
                          volume)

    def _cleanup(self):
        bExists = os.path.exists(self.config_file_path)
        if bExists:
            os.remove(self.config_file_path)
        shutil.rmtree(self.tempdir)


class VMAXFCDriverFastTestCase(test.TestCase):

    def setUp(self):

        self.data = VMAXCommonData()

        self.tempdir = tempfile.mkdtemp()
        super(VMAXFCDriverFastTestCase, self).setUp()
        self.config_file_path = None
        self.create_fake_config_file_fast()
        self.addCleanup(self._cleanup)

        self.flags(rpc_backend='oslo_messaging._drivers.impl_fake')
        configuration = mock.Mock()
        configuration.cinder_emc_config_file = self.config_file_path
        configuration.safe_get.return_value = 'FCFAST'
        configuration.config_group = 'FCFAST'

        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         self.fake_is_v3)
        self.mock_object(utils.VMAXUtils, '_is_sync_complete',
                         return_value=True)
        self.mock_object(cinder_utils, 'get_bool_param',
                         return_value=False)
        driver = fc.VMAXFCDriver(configuration=configuration)
        driver.db = FakeDB()
        driver.common.conn = FakeEcomConnection()
        driver.zonemanager_lookup_service = None
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)
        self.driver.masking = masking.VMAXMasking('FC')

    def create_fake_config_file_fast(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        fastPolicy = doc.createElement("FastPolicy")
        fastPolicyText = doc.createTextNode("GOLD1")
        emc.appendChild(fastPolicy)
        fastPolicy.appendChild(fastPolicyText)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("gold")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        filename = 'cinder_emc_config_FCFAST.xml'

        self.config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()

    def fake_ecom_connection(self):
        conn = FakeEcomConnection()
        return conn

    def fake_is_v3(self, conn, serialNumber):
        return False

    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=2.0)
    @mock.patch.object(
        fast.VMAXFast,
        'get_capacities_associated_to_policy',
        return_value=(1234, 1200, 1200, 1))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_pool_capacities',
        return_value=(1234, 1200, 1200, 1))
    @mock.patch.object(
        fast.VMAXFast,
        'get_tier_policy_by_name',
        return_value=None)
    @mock.patch.object(
        fast.VMAXFast,
        'is_tiering_policy_enabled',
        return_value=True)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storageSystem',
        return_value=None)
    def test_get_volume_stats_fast(self,
                                   mock_storage_system,
                                   mock_is_fast_enabled,
                                   mock_get_policy,
                                   mock_pool_capacities,
                                   mock_capacities_associated_to_policy,
                                   mock_or):
        self.driver.get_volume_stats(True)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_volume_fast_success(
            self, _mock_volume_type, mock_storage_system, mock_pool_policy):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'storagetype: stripedmetacount': '4',
                      'volume_backend_name': 'FCFAST'})
    def test_create_volume_fast_striped_success(
            self, _mock_volume_type, mock_storage_system, mock_pool_policy):
        self.driver.create_volume(self.data.test_volume_v2)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_volume_in_CG_fast_success(
            self, _mock_volume_type, mock_storage_system, mock_pool_policy):
        self.driver.create_volume(self.data.test_volume_CG)

    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_delete_volume_fast_success(self, _mock_volume_type,
                                        mock_storage_group):
        self.driver.delete_volume(self.data.test_volume)

    def test_create_volume_fast_failed(self):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume,
                          self.data.test_failed_volume)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_delete_volume_fast_notfound(self, _mock_volume_type):
        """"Test delete volume with volume not found."""
        notfound_delete_vol = {}
        notfound_delete_vol['name'] = 'notfound_delete_vol'
        notfound_delete_vol['id'] = '10'
        notfound_delete_vol['CreationClassName'] = 'Symmm_StorageVolume'
        notfound_delete_vol['SystemName'] = self.data.storage_system
        notfound_delete_vol['DeviceID'] = notfound_delete_vol['id']
        notfound_delete_vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        notfound_delete_vol['host'] = self.data.fake_host
        name = {}
        name['classname'] = 'Symm_StorageVolume'
        keys = {}
        keys['CreationClassName'] = notfound_delete_vol['CreationClassName']
        keys['SystemName'] = notfound_delete_vol['SystemName']
        keys['DeviceID'] = notfound_delete_vol['DeviceID']
        keys['SystemCreationClassName'] = (
            notfound_delete_vol['SystemCreationClassName'])
        name['keybindings'] = keys
        notfound_delete_vol['volume_type_id'] = 'abc'
        notfound_delete_vol['provider_location'] = None

        self.driver.delete_volume(notfound_delete_vol)

    @mock.patch.object(
        utils.VMAXUtils,
        'wait_for_job_complete',
        return_value=(-1, 'error'))
    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        masking.VMAXMasking,
        '_wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_delete_volume_fast_failed(
            self, _mock_volume_type, mock_wrapper,
            mock_storage_system, mock_pool_policy, mock_wait):
        self.driver.create_volume(self.data.failed_delete_vol)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.delete_volume,
                          self.data.failed_delete_vol)

    @mock.patch.object(
        common.VMAXCommon,
        '_is_same_host',
        return_value=True)
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=VMAXCommonData.lunmaskctrl_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_map_fast_success(self, _mock_volume_type, mock_maskingview,
                              mock_is_same_host):
        common = self.driver.common
        common.get_target_wwns_list = mock.Mock(
            return_value=VMAXCommonData.target_wwns)
        self.driver.common._get_correct_port_group = mock.Mock(
            return_value=self.data.port_group)
        data = self.driver.initialize_connection(
            self.data.test_volume, self.data.connector)
        # Test the no lookup service, pre-zoned case.
        common.get_target_wwns_list.assert_called_once_with(
            VMAXCommonData.storage_system, self.data.test_volume,
            VMAXCommonData.connector)
        for init, target in data['data']['initiator_target_map'].items():
            self.assertIn(init[::-1], target)

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'Name': "0001"}, False, {}))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_map_fast_failed(self, _mock_volume_type, mock_wrap_device):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.initialize_connection,
                          self.data.test_volume,
                          self.data.connector)

    @mock.patch.object(
        common.VMAXCommon,
        'check_ig_instance_name',
        return_value='myInitGroup')
    @mock.patch.object(
        common.VMAXCommon,
        'get_masking_views_by_port_group',
        return_value=[])
    @mock.patch.object(
        masking.VMAXMasking,
        'get_initiator_group_from_masking_view',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_initiator_masking_group',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_by_volume',
        return_value=VMAXCommonData.lunmaskctrl_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_detach_fast_success(self, mock_volume_type, mock_maskingview,
                                 mock_ig, mock_igc, mock_mv, mock_check_ig):
        common = self.driver.common
        common.get_target_wwns_list = mock.Mock(
            return_value=VMAXCommonData.target_wwns)
        data = self.driver.terminate_connection(self.data.test_volume,
                                                self.data.connector)
        common.get_target_wwns_list.assert_called_once_with(
            VMAXCommonData.storage_system, self.data.test_volume,
            VMAXCommonData.connector)
        numTargetWwns = len(VMAXCommonData.target_wwns)
        self.assertEqual(numTargetWwns, len(data['data']))

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_size',
        return_value='2147483648')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_extend_volume_fast_success(self, _mock_volume_type,
                                        _mock_volume_size):
        newSize = '2'
        self.driver.extend_volume(self.data.test_volume, newSize)

    @mock.patch.object(
        utils.VMAXUtils,
        'check_if_volume_is_extendable',
        return_value='False')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_extend_volume_striped_fast_failed(self,
                                               _mock_volume_type,
                                               _mock_is_extendable):
        newSize = '2'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.extend_volume,
                          self.data.test_volume,
                          newSize)

    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_snapshot_different_sizes_meta_fast_success(
            self, mock_volume_type,
            mock_meta, mock_size, mock_pool, mock_policy):
        common = self.driver.common

        volumeDict = {'classname': u'Symm_StorageVolume',
                      'keybindings': VMAXCommonData.keybindings}
        common.provision.create_volume_from_pool = (
            mock.Mock(return_value=(volumeDict, 0)))
        common.provision.get_volume_dict_from_job = (
            mock.Mock(return_value=volumeDict))
        common.fast.is_volume_in_default_SG = (
            mock.Mock(return_value=True))
        self.driver.create_snapshot(self.data.test_snapshot)

    @mock.patch.object(
        utils.VMAXUtils,
        'parse_file_to_get_array_map',
        return_value=None)
    def test_create_snapshot_fast_failed(self, mock_pool):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_snapshot,
                          self.data.test_snapshot)

    @unittest.skip("Skip until bug #1578986 is fixed")
    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_volume_from_same_size_meta_snapshot(
            self, mock_volume_type, mock_sync_sv, mock_meta, mock_size,
            mock_compare):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        common = self.driver.common
        common.fast.is_volume_in_default_SG = mock.Mock(return_value=True)
        self.driver.create_volume_from_snapshot(
            self.data.test_volume, self.data.test_volume)

    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=False)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    @mock.patch.object(
        utils.VMAXUtils,
        'find_replication_service',
        return_value=None)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST',
                      'FASTPOLICY': 'FC_GOLD1'})
    def test_create_volume_from_snapshot_fast_failed(
            self, mock_volume_type, mock_rep_service, mock_sync_sv,
            mock_license):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume_from_snapshot,
                          self.data.test_volume,
                          VMAXCommonData.test_source_volume)

    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    def test_create_clone_simple_volume_fast_success(self, mock_compare):
        extraSpecs = {'storagetype:fastpolicy': 'FC_GOLD1',
                      'volume_backend_name': 'FCFAST',
                      'isV3': False}
        self.driver.common._initial_setup = (
            mock.Mock(return_value=extraSpecs))
        self.driver.common.extraSpecs = extraSpecs
        self.driver.utils.is_clone_licensed = (
            mock.Mock(return_value=True))
        FakeDB.volume_get = (
            mock.Mock(return_value=VMAXCommonData.test_source_volume))
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.driver.common.fast.is_volume_in_default_SG = (
            mock.Mock(return_value=True))
        self.driver.utils.isArrayV3 = mock.Mock(return_value=False)
        self.driver.common._find_storage_sync_sv_sv = (
            mock.Mock(return_value=(None, None)))
        self.driver.create_cloned_volume(self.data.test_volume,
                                         VMAXCommonData.test_source_volume)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_meta_members_capacity_in_byte',
        return_value=[1234567, 7654321])
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_meta_head',
        return_value=[VMAXCommonData.test_volume])
    @mock.patch.object(
        fast.VMAXFast,
        'get_pool_associated_to_policy',
        return_value=1)
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_clone_fast_failed(
            self, mock_volume_type, mock_vol, mock_policy,
            mock_meta, mock_size, mock_pool):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        self.driver.common._modify_and_get_composite_volume_instance = (
            mock.Mock(return_value=(1, None)))
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_cloned_volume,
                          self.data.test_volume,
                          VMAXCommonData.test_source_volume)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_migrate_volume_fast_success(self, _mock_volume_type):
        self.driver.migrate_volume(self.data.test_ctxt, self.data.test_volume,
                                   self.data.test_host)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_CG_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.create_consistencygroup(
            self.data.test_ctxt, self.data.test_CG)

    @mock.patch.object(
        FakeDB,
        'volume_get_all_by_group',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_delete_CG_no_volumes_fast_success(
            self, _mock_volume_type, _mock_storage_system,
            _mock_db_volumes):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_delete_CG_with_volumes_fast_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        utils.VMAXUtils,
        'find_group_sync_rg_by_target',
        return_value="")
    @mock.patch.object(
        common.VMAXCommon,
        '_get_members_of_replication_group',
        return_value=())
    @mock.patch.object(
        common.VMAXCommon,
        '_find_consistency_group',
        return_value=(
            VMAXCommonData.test_CG,
            VMAXCommonData.test_CG['name'] + "_" + (
                VMAXCommonData.test_CG['id'])))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_create_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage, _mock_cg, _mock_members,
            _mock_rg):
        self.driver.create_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'FCFAST'})
    def test_delete_snapshot_for_CG_no_fast_success(
            self, _mock_volume_type, _mock_storage):
        self.driver.delete_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    # Bug 1385450
    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=False)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_replication_service_capabilities',
        return_value={'InstanceID': 'SYMMETRIX+1385450'})
    def test_create_clone_without_license(self, mock_service, mock_license):
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_cloned_volume,
                          self.data.test_volume,
                          VMAXCommonData.test_source_volume)

    def test_manage_existing_fast_failed(self):
        volume = {}
        metadata = {'key': 'array',
                    'value': '12345'}
        poolInstanceName = {}
        storageSystem = {}
        poolInstanceName['InstanceID'] = "SATA_GOLD1"
        storageSystem['InstanceID'] = "SYMMETRIX+00019870000"
        volume['volume_metadata'] = [metadata]
        volume['name'] = "test-volume"
        volume['host'] = 'HostX@Backend#Bronze+SRP_1+1234567891011'
        external_ref = {'source-name': '0123'}
        common = self.driver.common
        common._initial_setup = mock.Mock(
            return_value={'volume_backend_name': 'FCFAST',
                          'storagetype:fastpolicy': 'GOLD'})
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.manage_existing,
                          volume,
                          external_ref)

    def _cleanup(self):
        bExists = os.path.exists(self.config_file_path)
        if bExists:
            os.remove(self.config_file_path)
        shutil.rmtree(self.tempdir)


class EMCV3DriverTestCase(test.TestCase):

    def setUp(self):

        self.data = VMAXCommonData()

        self.data.storage_system = 'SYMMETRIX-+-000197200056'

        self.tempdir = tempfile.mkdtemp()
        super(EMCV3DriverTestCase, self).setUp()
        self.config_file_path = None
        self.create_fake_config_file_v3()
        self.addCleanup(self._cleanup)
        self.flags(rpc_backend='oslo_messaging._drivers.impl_fake')
        self.set_configuration()

    def set_configuration(self):
        configuration = mock.MagicMock()
        configuration.cinder_emc_config_file = self.config_file_path
        configuration.config_group = 'V3'

        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        self.mock_object(cinder_utils, 'get_bool_param',
                         return_value=False)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         self.fake_is_v3)
        self.patcher = mock.patch(
            'oslo_service.loopingcall.FixedIntervalLoopingCall',
            new=unit_utils.ZeroIntervalLoopingCall)
        self.patcher.start()

        driver = fc.VMAXFCDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver

    def create_fake_config_file_v3(self):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("SRP_1")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        slo = doc.createElement("ServiceLevel")
        slotext = doc.createTextNode("Bronze")
        emc.appendChild(slo)
        slo.appendChild(slotext)

        workload = doc.createElement("Workload")
        workloadtext = doc.createTextNode("DSS")
        emc.appendChild(workload)
        workload.appendChild(workloadtext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        filename = 'cinder_emc_config_V3.xml'

        self.config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()

    def fake_ecom_connection(self):
        self.conn = FakeEcomConnection()
        return self.conn

    def fake_is_v3(self, conn, serialNumber):
        return True

    def fake_gather_info(self):
        return

    def default_extraspec(self):
        return {'storagetype:pool': 'SRP_1',
                'volume_backend_name': 'V3_BE',
                'storagetype:workload': 'DSS',
                'storagetype:slo': 'Bronze',
                'storagetype:array': '1234567891011',
                'isV3': True,
                'portgroupname': 'OS-portgroup-PG'}

    def default_vol(self):
        vol = EMC_StorageVolume()
        vol['name'] = self.data.test_volume['name']
        vol['CreationClassName'] = 'Symm_StorageVolume'
        vol['ElementName'] = self.data.test_volume['id']
        vol['DeviceID'] = self.data.test_volume['device_id']
        vol['Id'] = self.data.test_volume['id']
        vol['SystemName'] = self.data.storage_system
        vol['NumberOfBlocks'] = self.data.test_volume['NumberOfBlocks']
        vol['BlockSize'] = self.data.test_volume['BlockSize']
        # Added vol to vol.path
        vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        vol.path = vol
        vol.path.classname = vol['CreationClassName']
        return vol

    def default_storage_group(self):
        storagegroup = {}
        storagegroup['CreationClassName'] = (
            self.data.storagegroup_creationclass)
        storagegroup['ElementName'] = 'no_masking_view'
        return storagegroup

    @mock.patch.object(
        masking.VMAXMasking,
        '_delete_mv_ig_and_sg')
    def test_last_vol_in_SG_with_MV(self, mock_delete):
        conn = self.fake_ecom_connection()
        common = self.driver.common
        controllerConfigService = (
            common.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        extraSpecs = self.default_extraspec()

        storageGroupName = self.data.storagegroupname
        storageGroupInstanceName = (
            common.utils.find_storage_masking_group(
                conn, controllerConfigService, storageGroupName))
        vol = self.default_vol()
        self.assertTrue(common.masking._last_vol_in_SG(
            conn, controllerConfigService, storageGroupInstanceName,
            storageGroupName, vol, vol['name'], extraSpecs))

    def test_last_vol_in_SG_no_MV(self):
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.common.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        extraSpecs = self.default_extraspec()
        self.driver.common.masking.get_masking_view_from_storage_group = (
            mock.Mock(return_value=None))
        self.driver.common.masking.utils.get_existing_instance = (
            mock.Mock(return_value=None))
        storagegroup = self.default_storage_group()

        vol = self.default_vol()
        self.assertTrue(self.driver.common.masking._last_vol_in_SG(
            conn, controllerConfigService, storagegroup,
            storagegroup['ElementName'], vol, vol['name'], extraSpecs))

    def test_last_vol_in_SG_no_MV_fail(self):
        self.driver.common.masking.utils.get_existing_instance = (
            mock.Mock(return_value='value'))
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.common.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        extraSpecs = self.default_extraspec()
        vol = self.default_vol()
        storagegroup = self.default_storage_group()
        storagegroup['ElementName'] = 'no_masking_view'

        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common.masking._last_vol_in_SG,
                          conn, controllerConfigService,
                          storagegroup, storagegroup['ElementName'], vol,
                          vol['name'], extraSpecs)

    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=2.0)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storageSystem',
        return_value={'Name': VMAXCommonData.storage_system_v3})
    def test_get_volume_stats_v3(
            self, mock_storage_system, mock_or):
        self.driver.common.pool_info['reserved_percentage'] = 5
        self.driver.get_volume_stats(True)
        self.driver.common.pool_info['reserved_percentage'] = 0

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_volume_v3_success(
            self, _mock_volume_type, mock_storage_system):
        self.data.test_volume_v3['host'] = self.data.fake_host_v3
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.common._get_or_create_storage_group_v3 = mock.Mock(
            return_value = self.data.default_sg_instance_name)
        self.driver.create_volume(self.data.test_volume_v3)

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=(VMAXCommonData.extra_specs_no_slo))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_or_create_storage_group_v3',
        return_value=(VMAXCommonData.default_sg_instance_name))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_volume_v3_no_slo_success(
            self, _mock_volume_type, mock_storage_system, mock_sg,
            mock_initial_setup):
        # This the no fast scenario
        v3_vol = self.data.test_volume_v3
        v3_vol['host'] = 'HostX@Backend#NONE+SRP_1+1234567891011'
        self.driver.create_volume(v3_vol)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_volume_v3_slo_NONE_success(
            self, _mock_volume_type, mock_storage_system):
        # NONE is a valid SLO
        v3_vol = self.data.test_volume_v3
        v3_vol['host'] = 'HostX@Backend#NONE+SRP_1+1234567891011'
        instid = 'SYMMETRIX-+-000197200056-+-NONE:DSS-+-F-+-0-+-SR-+-SRP_1'
        storagepoolsetting = (
            {'InstanceID': instid,
             'CreationClassName': 'CIM_StoragePoolSetting'})
        self.driver.common.provisionv3.get_storage_pool_setting = mock.Mock(
            return_value=storagepoolsetting)
        extraSpecs = {'storagetype:pool': 'SRP_1',
                      'volume_backend_name': 'V3_BE',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'NONE',
                      'storagetype:array': '1234567891011',
                      'isV3': True,
                      'portgroupname': 'OS-portgroup-PG'}
        self.driver.common._initial_setup = mock.Mock(
            return_value=extraSpecs)
        self.driver.common._get_or_create_storage_group_v3 = mock.Mock(
            return_value = self.data.default_sg_instance_name)

        self.driver.create_volume(v3_vol)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_volume_v3_invalid_slo_failed(
            self, _mock_volume_type, mock_storage_system):
        extraSpecs = {'storagetype:pool': 'SRP_1',
                      'volume_backend_name': 'V3_BE',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bogus',
                      'storagetype:array': '1234567891011',
                      'isV3': True,
                      'portgroupname': 'OS-portgroup-PG'}
        self.driver.common._initial_setup = mock.Mock(
            return_value=extraSpecs)

        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume,
                          self.data.test_volume)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_volume_in_CG_v3_success(
            self, _mock_volume_type, mock_storage_system):
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.common._get_or_create_storage_group_v3 = mock.Mock(
            return_value = self.data.default_sg_instance_name)
        self.driver.create_volume(self.data.test_volume_CG_v3)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_delete_volume_v3_success(self, _mock_volume_type):
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.delete_volume(self.data.test_volume_v3)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_v3_default_sg_instance_name',
        return_value=(None, None, VMAXCommonData.default_sg_instance_name))
    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_snapshot_v3_success(
            self, mock_type, mock_pool, mock_licence, mock_sg):
        common = self.driver.common
        with mock.patch.object(common, '_initial_setup',
                               return_value=self.default_extraspec()):
            self.driver.create_snapshot(self.data.test_snapshot_v3)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_delete_snapshot_v3_success(self, mock_volume_type):
        self.data.test_volume_v3['volume_name'] = "vmax-1234567"
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.delete_snapshot(self.data.test_snapshot_v3)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_v3_default_sg_instance_name',
        return_value=(None, None, VMAXCommonData.default_sg_instance_name))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_or_create_storage_group_v3',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=True)
    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume)
    def test_create_cloned_volume_v3_success(
            self, mock_volume_db, mock_type, mock_pool, mock_compare,
            mock_licence, mock_sg, mock_sg_name):
        sourceVol = self.data.test_volume_v3.copy()
        sourceVol['volume_name'] = "vmax-1234567"
        sourceVol['size'] = 100
        cloneVol = {}
        cloneVol['name'] = 'vol1'
        cloneVol['id'] = '1'
        cloneVol['CreationClassName'] = 'Symmm_StorageVolume'
        cloneVol['SystemName'] = self.data.storage_system
        cloneVol['DeviceID'] = cloneVol['id']
        cloneVol['SystemCreationClassName'] = 'Symm_StorageSystem'
        cloneVol['volume_type_id'] = 'abc'
        cloneVol['provider_location'] = None
        cloneVol['NumberOfBlocks'] = 100
        cloneVol['BlockSize'] = self.data.block_size
        cloneVol['host'] = self.data.fake_host_v3
        cloneVol['size'] = 100
        common = self.driver.common
        conn = FakeEcomConnection()
        sourceInstance = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        with mock.patch.object(common, '_initial_setup',
                               return_value=self.default_extraspec()):
            with mock.patch.object(common, '_find_lun',
                                   return_value=sourceInstance):
                self.driver.create_cloned_volume(cloneVol, sourceVol)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_create_CG_v3_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.create_consistencygroup(
            self.data.test_ctxt, self.data.test_volume_CG_v3)

    @mock.patch.object(
        FakeDB,
        'volume_get_all_by_group',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_delete_CG_no_volumes_v3_success(
            self, _mock_volume_type, _mock_storage_system,
            _mock_db_volumes):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_delete_CG_with_volumes_v3_success(
            self, _mock_volume_type, _mock_storage_system):
        self.driver.delete_consistencygroup(
            self.data.test_ctxt, self.data.test_CG, [])

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_migrate_volume_v3_success(self, _mock_volume_type):
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.migrate_volume(self.data.test_ctxt, self.data.test_volume,
                                   self.data.test_host)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_element_name',
        return_value='1')
    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        '_find_new_storage_group',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        utils.VMAXUtils,
        'wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        utils.VMAXUtils,
        '_get_fast_settings_from_storage_group',
        return_value='Gold+DSS_REP')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_retype_volume_v3_success(
            self, _mock_volume_type, mock_fast_settings,
            mock_storage_group, mock_found_SG, mock_element_name):
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.assertTrue(self.driver.retype(
            self.data.test_ctxt, self.data.test_volume_v3, self.data.new_type,
            self.data.diff, self.data.test_host_v3))

    @mock.patch.object(
        utils.VMAXUtils,
        '_get_fast_settings_from_storage_group',
        return_value='Bronze+DSS')
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_retype_volume_same_host_failure(
            self, _mock_volume_type, mock_fast_settings):
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.assertFalse(self.driver.retype(
            self.data.test_ctxt, self.data.test_volume_v3, self.data.new_type,
            self.data.diff, self.data.test_host_v3))

    @mock.patch.object(
        utils.VMAXUtils,
        'find_volume_instance',
        return_value=(
            FakeEcomConnection().EnumerateInstanceNames(
                "EMC_StorageVolume")[0]))
    @mock.patch.object(
        common.VMAXCommon,
        '_create_v3_volume',
        return_value=(0, {}, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'find_group_sync_rg_by_target',
        return_value=1)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_members_of_replication_group',
        return_value=())
    @mock.patch.object(
        common.VMAXCommon,
        '_find_consistency_group',
        return_value=(
            VMAXCommonData.test_CG,
            VMAXCommonData.test_CG['name'] + "_" + (
                VMAXCommonData.test_CG['id'])))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volumetype_extraspecs',
        return_value={'pool_name': u'Bronze+DSS+SRP_1+1234567891011'})
    def test_create_cgsnapshot_v3_success(
            self, _mock_volume_type, _mock_storage, _mock_cg,
            _mock_members, mock_rg, mock_create_vol, mock_find):
        volume = {}
        snapshot = {}
        snapshots = []
        volume['volume_type_id'] = 'abc'
        volume['size'] = '123'
        volume['id'] = '123'
        snapshot['volume'] = volume
        snapshot['id'] = '456'
        snapshots.append(snapshot)
        provisionv3 = self.driver.common.provisionv3
        provisionv3.create_group_replica = mock.Mock(return_value=(0, None))
        self.driver.create_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, snapshots)
        repServ = self.conn.EnumerateInstanceNames("EMC_ReplicationService")[0]
        intervals_retries_dict = (
            {'storagetype:interval': 0, 'storagetype:retries': 0})
        provisionv3.create_group_replica.assert_called_once_with(
            self.conn, repServ,
            VMAXCommonData.test_CG,
            VMAXCommonData.test_CG, '84ab',
            intervals_retries_dict)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_delete_cgsnapshot_v3_success(
            self, _mock_volume_type, _mock_storage):
        self.driver.delete_cgsnapshot(
            self.data.test_ctxt, self.data.test_CG_snapshot, [])

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system_v3))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_update_CG_add_volume_v3_success(
            self, _mock_volume_type, _mock_storage_system):
        add_volumes = []
        add_volumes.append(self.data.test_source_volume)
        remove_volumes = None
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Multiple volumes
        add_volumes.append(self.data.test_source_volume)
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Can't find CG
        self.driver.common._find_consistency_group = mock.Mock(
            return_value=(None, 'cg_name'))
        self.assertRaises(exception.ConsistencyGroupNotFound,
                          self.driver.update_consistencygroup,
                          self.data.test_ctxt, self.data.test_CG,
                          add_volumes, remove_volumes)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system_v3))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_update_CG_remove_volume_v3_success(
            self, _mock_volume_type, _mock_storage_system):
        remove_volumes = []
        remove_volumes.append(self.data.test_source_volume)
        add_volumes = None
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)
        # Multiple volumes
        remove_volumes.append(self.data.test_source_volume)
        self.driver.update_consistencygroup(
            self.data.test_ctxt, self.data.test_CG,
            add_volumes, remove_volumes)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_element_name',
        return_value='1')
    @mock.patch.object(
        common.VMAXCommon,
        '_is_same_host',
        return_value=True)
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=VMAXCommonData.lunmaskctrl_name)
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_map_v3_success(
            self, _mock_volume_type, mock_maskingview, mock_is_same_host,
            mock_element_name):
        common = self.driver.common
        common.get_target_wwns_list = mock.Mock(
            return_value=VMAXCommonData.target_wwns)
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.common._get_correct_port_group = mock.Mock(
            return_value=self.data.port_group)
        data = self.driver.initialize_connection(
            self.data.test_volume_v3, self.data.connector)
        # Test the no lookup service, pre-zoned case.
        common.get_target_wwns_list.assert_called_once_with(
            VMAXCommonData.storage_system, self.data.test_volume_v3,
            VMAXCommonData.connector)
        for init, target in data['data']['initiator_target_map'].items():
            self.assertIn(init[::-1], target)

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'Name': "0001"}, False, {}))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_map_v3_failed(self, _mock_volume_type, mock_wrap_device):
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.initialize_connection,
                          self.data.test_volume,
                          self.data.connector)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_port_group_from_masking_view',
        return_value='myPortGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        'remove_and_reset_members')
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_element_name',
        return_value='1')
    @mock.patch.object(
        common.VMAXCommon,
        'check_ig_instance_name',
        return_value='myInitGroup')
    @mock.patch.object(
        common.VMAXCommon,
        'get_masking_views_by_port_group',
        return_value=[])
    @mock.patch.object(
        masking.VMAXMasking,
        'get_initiator_group_from_masking_view',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        '_find_initiator_masking_group',
        return_value='myInitGroup')
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=[VMAXCommonData.mv_instance_name])
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    def test_detach_v3_success(self, mock_volume_type, mock_maskingview,
                               mock_ig, mock_igc, mock_mv, mock_check_ig,
                               mock_element_name, mock_remove, mock_pg):
        common = self.driver.common
        with mock.patch.object(common, 'get_target_wwns_list',
                               return_value=VMAXCommonData.target_wwns):
            with mock.patch.object(common, '_initial_setup',
                                   return_value=self.default_extraspec()):
                data = self.driver.terminate_connection(
                    self.data.test_volume_v3, self.data.connector)
                common.get_target_wwns_list.assert_called_once_with(
                    VMAXCommonData.storage_system,
                    self.data.test_volume_v3,
                    VMAXCommonData.connector)
                numTargetWwns = len(VMAXCommonData.target_wwns)
                self.assertEqual(numTargetWwns, len(data['data']))

    # Bug https://bugs.launchpad.net/cinder/+bug/1440154
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    @mock.patch.object(
        FakeDB,
        'volume_get',
        return_value=VMAXCommonData.test_source_volume_v3)
    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        'create_element_replica')
    @mock.patch.object(
        utils.VMAXUtils,
        'find_sync_sv_by_volume',
        return_value=(None, None))
    def test_create_clone_v3_assert_clean_up_target_volume(
            self, mock_sync, mock_create_replica, mock_volume_db,
            mock_type, moke_pool):
        self.data.test_volume['volume_name'] = "vmax-1234567"
        e = exception.VolumeBackendAPIException('CreateElementReplica Ex')
        common = self.driver.common
        common.utils.is_clone_licensed = (
            mock.Mock(return_value=True))
        volumeDict = {'classname': u'Symm_StorageVolume',
                      'keybindings': VMAXCommonData.keybindings}
        common._create_v3_volume = (
            mock.Mock(return_value=(0, volumeDict, self.data.storage_system)))
        conn = self.fake_ecom_connection()
        storageConfigService = []
        storageConfigService = {}
        storageConfigService['SystemName'] = VMAXCommonData.storage_system
        storageConfigService['CreationClassName'] = (
            self.data.stconf_service_creationclass)
        common._delete_from_pool_v3 = mock.Mock(return_value=0)
        mock_create_replica.side_effect = e
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_cloned_volume,
                          self.data.test_volume_v3,
                          VMAXCommonData.test_source_volume_v3)
        extraSpecs = common._initial_setup(self.data.test_volume_v3)
        targetInstance = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        deviceID = targetInstance['DeviceID']
        common._delete_from_pool_v3(storageConfigService, targetInstance,
                                    targetInstance['Name'], deviceID,
                                    extraSpecs)
        common._delete_from_pool_v3.assert_called_with(storageConfigService,
                                                       targetInstance,
                                                       targetInstance['Name'],
                                                       deviceID,
                                                       extraSpecs)

    def test_get_remaining_slo_capacity_wlp(self):
        conn = self.fake_ecom_connection()
        array_info = {'Workload': u'DSS', 'SLO': u'Bronze'}
        storagesystem = self.data.storage_system_v3
        srpPoolInstanceName = {}
        srpPoolInstanceName['InstanceID'] = (
            self.data.storage_system_v3 + '+U+' + 'SRP_1')
        srpPoolInstanceName['CreationClassName'] = (
            'Symm_VirtualProvisioningPool')
        srpPoolInstanceName['ElementName'] = 'SRP_1'

        remainingCapacityGb = (
            self.driver.common.provisionv3._get_remaining_slo_capacity_wlp(
                conn, srpPoolInstanceName, array_info, storagesystem))
        remainingSLOCapacityGb = self.driver.common.utils.convert_bits_to_gbs(
            self.data.remainingSLOCapacity)
        self.assertEqual(remainingSLOCapacityGb, remainingCapacityGb)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_element_name',
        return_value='1')
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_size',
        return_value='2147483648')
    def test_extend_volume(self, mock_volume_size, mock_element_name):
        newSize = '2'
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.driver.extend_volume(self.data.test_volume_v3, newSize)

    def test_extend_volume_smaller_size_exception(self):
        test_local_volume = {'name': 'vol1',
                             'size': 4,
                             'volume_name': 'vol1',
                             'id': 'vol1',
                             'device_id': '1',
                             'provider_auth': None,
                             'project_id': 'project',
                             'display_name': 'vol1',
                             'display_description': 'test volume',
                             'volume_type_id': 'abc',
                             'provider_location': six.text_type(
                                 self.data.provider_location),
                             'status': 'available',
                             'host': self.data.fake_host_v3,
                             'NumberOfBlocks': 100,
                             'BlockSize': self.data.block_size
                             }
        newSize = '2'
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.default_extraspec())
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.extend_volume,
            test_local_volume, newSize)

    def test_extend_volume_exception(self):
        common = self.driver.common
        newsize = '2'
        common._initial_setup = mock.Mock(return_value=None)
        common._find_lun = mock.Mock(return_value=None)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            common.extend_volume,
            self.data.test_volume, newsize)

    def test_extend_volume_size_tally_exception(self):
        common = self.driver.common
        newsize = '2'
        self.driver.common._initial_setup = mock.Mock(
            return_value=self.data.extra_specs)
        vol = {'SystemName': self.data.storage_system}
        common._find_lun = mock.Mock(return_value=vol)
        common._extend_v3_volume = mock.Mock(return_value=(0, vol))
        common.utils.find_volume_instance = mock.Mock(
            return_value='2147483648')
        common.utils.get_volume_size = mock.Mock(return_value='2147483646')
        self.assertRaises(
            exception.VolumeBackendAPIException,
            common.extend_volume,
            self.data.test_volume, newsize)

    def _cleanup(self):
        bExists = os.path.exists(self.config_file_path)
        if bExists:
            os.remove(self.config_file_path)
        shutil.rmtree(self.tempdir)


class EMCV3MultiPoolDriverTestCase(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()
        self.vol_v3 = self.data.test_volume_v4
        self.vol_v3['provider_location'] = (
            six.text_type(self.data.provider_location_multi_pool))

        super(EMCV3MultiPoolDriverTestCase, self).setUp()
        self.set_configuration()

    def set_configuration(self):
        configuration = mock.Mock()
        configuration.safe_get.return_value = 'MULTI_POOL_V3'
        configuration.config_group = 'MULTI_POOL_V3'
        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        self.mock_object(common.VMAXCommon, '_gather_info',
                         self.fake_gather_info)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         return_value=True)
        self.mock_object(utils.VMAXUtils, '_is_sync_complete',
                         return_value=True)
        self.mock_object(common.VMAXCommon,
                         '_get_multi_pool_support_enabled_flag',
                         return_value=True)
        driver = fc.VMAXFCDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    def create_fake_config_file_multi_pool_v3(self, tempdir):
        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("SRP_1")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        filename = 'cinder_emc_config_V3.xml'

        config_file_path = tempdir + '/' + filename

        f = open(config_file_path, 'w')
        doc.writexml(f)
        f.close()
        return config_file_path

    def create_fake_config_file_legacy_v3(self, tempdir):

        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("SRP_1")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        slo = doc.createElement("ServiceLevel")
        slotext = doc.createTextNode("Silver")
        emc.appendChild(slo)
        slo.appendChild(slotext)

        workload = doc.createElement("Workload")
        workloadtext = doc.createTextNode("OLTP")
        emc.appendChild(workload)
        workload.appendChild(workloadtext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        filename = 'cinder_emc_config_V3.xml'

        config_file_path = tempdir + '/' + filename

        f = open(config_file_path, 'w')
        doc.writexml(f)
        f.close()
        return config_file_path

    def fake_ecom_connection(self):
        self.conn = FakeEcomConnection()
        return self.conn

    def fake_gather_info(self):
        return

    def default_array_info_list(self):
        return [{'EcomServerIp': u'1.1.1.1',
                 'EcomServerPort': 10,
                 'EcomUserName': u'user',
                 'EcomPassword': u'pass',
                 'PoolName': u'SRP_1',
                 'PortGroup': u'OS-portgroup-PG',
                 'SerialNumber': 1234567891011,
                 'SLO': u'Bronze',
                 'Workload': u'DSS'}]

    def array_info_list_without_slo(self):
        return [{'EcomServerIp': u'1.1.1.1',
                 'EcomServerPort': 10,
                 'EcomUserName': u'user',
                 'EcomPassword': u'pass',
                 'PoolName': u'SRP_1',
                 'PortGroup': u'OS-portgroup-PG',
                 'SerialNumber': 1234567891011}]

    def multiple_array_info_list(self):
        return [{'EcomServerIp': u'1.1.1.1',
                 'EcomServerPort': 10,
                 'EcomUserName': u'user',
                 'EcomPassword': u'pass',
                 'PoolName': u'SRP_1',
                 'PortGroup': u'OS-portgroup-PG',
                 'SerialNumber': 1234567891011,
                 'SLO': u'Bronze',
                 'Workload': u'DSS'},
                {'EcomServerIp': u'1.1.1.1',
                 'EcomServerPort': 10,
                 'EcomUserName': u'user',
                 'EcomPassword': u'pass',
                 'PoolName': u'SRP_1',
                 'PortGroup': u'OS-portgroup-PG',
                 'SerialNumber': 1234567891011,
                 'SLO': u'Silver',
                 'Workload': u'OLTP'}]

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'MULTI_POOL_BE',
                      'pool_name': 'Bronze+DSS+SRP_1+1234567891011'})
    def test_initial_setup(self, mock_vol_types):
        tempdir = tempfile.mkdtemp()
        config_file_path = self.create_fake_config_file_multi_pool_v3(tempdir)
        with mock.patch.object(
                self.driver.common, '_register_config_file_from_config_group',
                return_value=config_file_path):
            extraSpecs = self.driver.common._initial_setup(self.vol_v3)
        self.assertEqual('SRP_1', extraSpecs['storagetype:pool'])
        self.assertEqual('DSS', extraSpecs['storagetype:workload'])
        self.assertEqual('Bronze', extraSpecs['storagetype:slo'])
        self.assertEqual('1234567891011', extraSpecs['storagetype:array'])
        self.assertEqual('OS-portgroup-PG', extraSpecs['portgroupname'])
        self.assertTrue(extraSpecs['isV3'])
        self.assertTrue(extraSpecs['MultiPoolSupport'])
        self.assertEqual('Bronze+DSS+SRP_1+1234567891011',
                         extraSpecs['pool_name'])
        self._cleanup(tempdir, config_file_path)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'MULTI_POOL_BE',
                      'pool_name': 'Bronze+DSS+SRP_1+1234567891011'})
    def test_initial_setup_with_legacy_file(self, mock_vol_types):
        # Test with legacy config file and verify
        # if the values for SLO and workload are used from
        # the pool_name and not the config file
        tempdir = tempfile.mkdtemp()
        config_file_path = self.create_fake_config_file_legacy_v3(tempdir)
        with mock.patch.object(
                self.driver.common, '_register_config_file_from_config_group',
                return_value=config_file_path):
            extraSpecs = self.driver.common._initial_setup(self.vol_v3)
        self.assertEqual('DSS', extraSpecs['storagetype:workload'])
        self.assertEqual('Bronze', extraSpecs['storagetype:slo'])
        self._cleanup(tempdir, config_file_path)

    def test_initial_setup_invalid_volume(self):
        # Test with volume which don't have pool_name
        tempdir = tempfile.mkdtemp()
        config_file_path = self.create_fake_config_file_multi_pool_v3(tempdir)
        with mock.patch.object(
                self.driver.common, '_register_config_file_from_config_group',
                return_value=config_file_path):
            invalid_vol_v3 = self.data.test_volume_v4.copy()
            invalid_vol_v3.pop('host', None)
            self.assertRaises(exception.VolumeBackendAPIException,
                              self.driver.common._initial_setup,
                              invalid_vol_v3)
        self._cleanup(tempdir, config_file_path)

    def test_validate_pool(self):
        v3_valid_pool = self.data.test_volume_v4.copy()
        # Pool aware scheduler enabled
        v3_valid_pool['host'] = self.data.fake_host_3_v3
        # Validate pool uses extraSpecs as a new argument
        # Use default extraSpecs as the argument
        pool = self.driver.common._validate_pool(
            v3_valid_pool, self.data.multi_pool_extra_specs)
        self.assertEqual('Bronze+DSS+SRP_1+1234567891011', pool)

    def test_validate_pool_invalid_pool_name(self):
        # Validate using older volume dictionary
        # and check if a exception is raised if multi_pool_support
        # is enabled and pool_name is not specified
        extraSpecs = self.data.multi_pool_extra_specs
        invalid_pool_name = extraSpecs.copy()
        invalid_pool_name['pool_name'] = 'not_valid'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common._validate_pool,
                          self.data.test_volume_v4, invalid_pool_name)

    def test_validate_pool_invalid_host(self):
        # Cannot get the pool from the host
        v3_valid_pool = self.data.test_volume_v4.copy()
        v3_valid_pool['host'] = 'HostX@Backend'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common._validate_pool,
                          v3_valid_pool)

    def test_validate_pool_legacy(self):
        # Legacy test. Provider Location does not have the version
        v3_valid_pool = self.data.test_volume_v4.copy()
        v3_valid_pool['host'] = self.data.fake_host_3_v3
        v3_valid_pool['provider_location'] = self.data.provider_location
        pool = self.driver.common._validate_pool(v3_valid_pool)
        self.assertIsNone(pool)

    @mock.patch.object(
        utils.VMAXUtils,
        'override_ratio',
        return_value=2.0)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_storageSystem',
        return_value={'Name': VMAXCommonData.storage_system_v3})
    def test_get_volume_stats_v3(
            self, mock_storage_system, mock_or):
        self.driver.common.pool_info['reserved_percentage'] = 5
        self.driver.get_volume_stats(True)
        self.driver.common.pool_info['reserved_percentage'] = 0

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_or_create_storage_group_v3',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_create_volume_multi_slo_success(
            self, mock_storage_system, mock_sg, mock_is):
        self.vol_v3['host'] = self.data.fake_host_3_v3
        self.vol_v3['provider_location'] = None
        model_update = self.driver.create_volume(self.vol_v3)
        # Verify if the device id is provided in the output
        provider_location = model_update['provider_location']
        provider_location = ast.literal_eval(provider_location)
        keybindings = provider_location['keybindings']
        device_id = keybindings['DeviceID']
        self.assertEqual('1', device_id)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_associated_masking_groups_from_device',
        return_value=VMAXCommonData.storagegroups)
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_delete_volume_multi_slo_success(
            self, mock_storage_system, mock_is, mock_mv):
        provider_location = (
            {'classname': 'Symm_StorageVolume',
             'keybindings':
             {'CreationClassName': 'Symm_StorageVolume',
              'SystemName': 'SYMMETRIX+000195900551',
              'DeviceID': '1',
              'SystemCreationClassName': 'Symm_StorageSystem'
              }
             })
        volumeInstanceName = (
            {'NumberOfBlocks': 100,
             'ElementName': '1',
             'Name': 'vol1',
             'BlockSize': 512,
             'provider_location': six.text_type(provider_location),
             'SystemName': 'SYMMETRIX+000195900551',
             'DeviceID': '1',
             'CreationClassName': 'Symm_StorageVolume',
             'Id': '1',
             'SystemCreationClassName': 'Symm_StorageSystem'})
        self.driver.delete_volume(self.vol_v3)
        masking = self.driver.common.masking
        get_groups_from_device = (
            masking.get_associated_masking_groups_from_device)
        get_groups_from_device.assert_called_once_with(
            self.conn, volumeInstanceName)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_or_create_storage_group_v3',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_create_volume_in_CG_multi_slo_success(
            self, mock_storage_system, mock_is, mock_sg):
        self.data.test_volume_CG_v3['provider_location'] = None
        model_update = self.driver.create_volume(self.data.test_volume_CG_v3)
        # Verify if the device id is provided in the output
        provider_location = model_update['provider_location']
        provider_location = ast.literal_eval(provider_location)
        keybindings = provider_location['keybindings']
        device_id = keybindings['DeviceID']
        self.assertEqual('1', device_id)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_element_name',
        return_value='1')
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        '_find_new_storage_group',
        return_value=VMAXCommonData.default_sg_instance_name)
    @mock.patch.object(
        utils.VMAXUtils,
        'wrap_get_storage_group_from_volume',
        return_value=None)
    @mock.patch.object(
        utils.VMAXUtils,
        '_get_fast_settings_from_storage_group',
        return_value='Gold+DSS_REP')
    def test_retype_volume_multi_slo_success(
            self, mock_fast_settings,
            mock_storage_group, mock_found_SG, mock_is, mock_element_name):
        self.assertTrue(self.driver.retype(
            self.data.test_ctxt, self.data.test_volume_v4, self.data.new_type,
            self.data.diff, self.data.test_host_1_v3))

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    # There is only one unique array in the conf file
    def test_create_CG_multi_slo_success(
            self, _mock_storage_system, mock_is):
        self.driver.create_consistencygroup(
            self.data.test_ctxt, self.data.test_CG)

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_members_of_replication_group',
        return_value=None)
    @mock.patch.object(
        FakeDB,
        'volume_get_all_by_group',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_delete_CG_no_volumes_multi_slo_success(
            self, _mock_storage_system,
            _mock_db_volumes, _mock_members, mock_is):
        # This is a CG delete with no volumes
        # there won't be a deleted status
        model_update = {}
        ret_model_update, ret_volumes_model_update = (
            self.driver.delete_consistencygroup(self.data.test_ctxt,
                                                self.data.test_CG, []))
        self.assertEqual(model_update, ret_model_update)

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_delete_CG_with_volumes_multi_slo_success(
            self, _mock_storage_system, mock_is):
        # Check for the status deleted after a successful delete CG
        model_update = {'status': 'deleted'}
        ret_model_update, ret_volumes_model_update = (
            self.driver.delete_consistencygroup(self.data.test_ctxt,
                                                self.data.test_CG, []))
        self.assertEqual(model_update, ret_model_update)

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    def test_migrate_volume_v3_success(self, mock_is):
        retVal, retList = self.driver.migrate_volume(
            self.data.test_ctxt, self.data.test_volume_v4,
            self.data.test_host_1_v3)
        self.assertTrue(retVal)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_volume_element_name',
        return_value='1')
    @mock.patch.object(
        utils.VMAXUtils,
        'get_v3_default_sg_instance_name',
        return_value=(None, None, VMAXCommonData.default_sg_instance_name))
    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_create_snapshot_v3_success(
            self, mock_pool, mock_is, mock_license, mock_sg, mock_element):
        self.data.test_volume_v4['volume_name'] = "vmax-1234567"
        self.driver.create_snapshot(self.data.test_snapshot_1_v3)
        utils = self.driver.common.provisionv3.utils
        utils.get_v3_default_sg_instance_name.assert_called_once_with(
            self.conn, u'SRP_1', u'Bronze', u'DSS', u'SYMMETRIX+000195900551',
            False)

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.multi_pool_extra_specs)
    def test_delete_snapshot_v3_success(self, mock_is):
        masking = self.driver.common.masking
        with mock.patch.object(
                masking, 'get_associated_masking_groups_from_device',
                return_value=self.data.storagegroups):
            self.driver.delete_snapshot(self.data.test_snapshot_1_v3)

    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        'get_srp_pool_stats',
        return_value=(100, 10, 1, 20, False))
    def test_update_volume_stats_single_array_info(self, mock_stats):
        self.driver.common.pool_info['reserved_percentage'] = 5
        self.driver.common.pool_info['arrays_info'] = (
            self.default_array_info_list())
        self.driver.common.multiPoolSupportEnabled = True
        data = self.driver.common.update_volume_stats()
        pools = data['pools']
        self.assertEqual("Bronze+DSS+SRP_1+1234567891011",
                         pools[0]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Bronze#DSS",
                         pools[0]['location_info'])
        self._cleanup_pool_info()

    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        'get_srp_pool_stats',
        return_value=(100, 10, 1, 20, False))
    def test_update_volume_stats_multiple_array_info_wlp_disabled(
            self, mock_stats):
        self.driver.common.pool_info['reserved_percentage'] = 5
        self.driver.common.pool_info['arrays_info'] = (
            self.multiple_array_info_list())
        self.driver.common.multiPoolSupportEnabled = True
        data = self.driver.common.update_volume_stats()
        pools = data['pools']
        self.assertEqual("Bronze+DSS+SRP_1+1234567891011",
                         pools[0]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Bronze#DSS",
                         pools[0]['location_info'])
        self.assertEqual("Silver+OLTP+SRP_1+1234567891011",
                         pools[1]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Silver#OLTP",
                         pools[1]['location_info'])
        self._cleanup_pool_info()

    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        'get_srp_pool_stats',
        return_value=(100, 10, 1, 20, False))
    def test_update_volume_stats_multiple_array_info_wlp_enabled(
            self, mock_stats):
        self.driver.common.pool_info['reserved_percentage'] = 5
        self.driver.common.pool_info['arrays_info'] = (
            self.multiple_array_info_list())
        self.driver.common.multiPoolSupportEnabled = True
        data = self.driver.common.update_volume_stats()
        pools = data['pools']
        self.assertEqual("Bronze+DSS+SRP_1+1234567891011",
                         pools[0]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Bronze#DSS",
                         pools[0]['location_info'])
        self.assertEqual("Silver+OLTP+SRP_1+1234567891011",
                         pools[1]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Silver#OLTP",
                         pools[1]['location_info'])
        self._cleanup_pool_info()

    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        'get_srp_pool_stats',
        return_value=(100, 10, 1, 20, False))
    def test_update_volume_stats_without_multi_pool(self, mock_stats):
        self.driver.common.pool_info['reserved_percentage'] = 5
        self.driver.common.pool_info['arrays_info'] = (
            self.multiple_array_info_list())
        data = self.driver.common.update_volume_stats()
        pools = data['pools']
        # Match with the older pool_name format
        self.assertEqual("Bronze+SRP_1+1234567891011",
                         pools[0]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Bronze#DSS",
                         pools[0]['location_info'])
        self.assertEqual("Silver+SRP_1+1234567891011",
                         pools[1]['pool_name'])
        self.assertEqual("1234567891011#SRP_1#Silver#OLTP",
                         pools[1]['location_info'])
        self._cleanup_pool_info()

    @mock.patch.object(
        common.VMAXCommon,
        '_find_pool_in_array',
        return_value=(VMAXCommonData.poolInstanceName,
                      VMAXCommonData.storage_system))
    def test_get_slo_workload_combinations_with_slo(self, mock_pool):
        self.driver.common.multiPoolSupportEnabled = True
        final_array_info_list = (
            self.driver.common._get_slo_workload_combinations(
                self.default_array_info_list()))
        bCheckForSilver = False
        for array_info in final_array_info_list:
            # Check if 'Silver' is present in the final list
            if array_info['SLO'] == 'Silver':
                bCheckForSilver = True
        self.assertTrue(bCheckForSilver)
        self._cleanup_pool_info()

    @mock.patch.object(
        common.VMAXCommon,
        '_find_pool_in_array',
        return_value=(VMAXCommonData.poolInstanceName,
                      VMAXCommonData.storage_system))
    def test_get_slo_workload_combinations_without_slo(self, mock_pool):
        self.driver.common.multiPoolSupportEnabled = True
        final_array_info_list = (
            self.driver.common._get_slo_workload_combinations(
                self.array_info_list_without_slo()))
        bCheckForSilver = False
        for array_info in final_array_info_list:
            # Check if 'Silver' is present in the final list
            if array_info['SLO'] == 'Silver':
                bCheckForSilver = True
        self.assertTrue(bCheckForSilver)
        self._cleanup_pool_info()

    def _cleanup(self, tempdir, config_file_path):
        bExists = os.path.exists(config_file_path)
        if bExists:
            os.remove(config_file_path)
        shutil.rmtree(tempdir)

    def _cleanup_pool_info(self):
        self.driver.common.pool_info['reserved_percentage'] = 0
        self.driver.common.pool_info['arrays_info'] = []
        self.driver.common.multiPoolSupportEnabled = False


class VMAXProvisionV3Test(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXProvisionV3Test, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'ProvisionV3Tests'
        configuration.config_group = 'ProvisionV3Tests'
        common.VMAXCommon._gather_info = mock.Mock()
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver

    def test_get_storage_pool_setting(self):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        slo = 'Bronze'
        workload = 'DSS'
        poolInstanceName = {}
        poolInstanceName['InstanceID'] = "SATA_GOLD1"
        poolInstanceName['CreationClassName'] = (
            self.data.storagepool_creationclass)

        storagePoolCapability = provisionv3.get_storage_pool_capability(
            conn, poolInstanceName)
        storagepoolsetting = provisionv3.get_storage_pool_setting(
            conn, storagePoolCapability, slo, workload)
        self.assertIn('Bronze:DSS', storagepoolsetting['InstanceID'])

    def test_get_storage_pool_setting_exception(self):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        slo = 'Bronze'
        workload = 'NONE'
        poolInstanceName = {}
        poolInstanceName['InstanceID'] = "SATA_GOLD1"
        poolInstanceName['CreationClassName'] = (
            self.data.storagepool_creationclass)

        storagePoolCapability = provisionv3.get_storage_pool_capability(
            conn, poolInstanceName)
        self.assertRaises(exception.VolumeBackendAPIException,
                          provisionv3.get_storage_pool_setting,
                          conn, storagePoolCapability, slo, workload)

    def test_extend_volume_in_SG(self):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        storageConfigService = {
            'CreationClassName': 'Symm_ElementCompositionService',
            'SystemName': 'SYMMETRIX+000195900551'}
        theVolumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        inVolumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeSize = 3

        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': True}
        job = {
            'Job': {'InstanceID': '9999', 'status': 'success', 'type': None}}
        conn.InvokeMethod = mock.Mock(return_value=(4096, job))
        provisionv3.utils.wait_for_job_complete = mock.Mock(return_value=(
            0, 'Success'))
        volumeDict = {'classname': u'Symm_StorageVolume',
                      'keybindings': VMAXCommonData.keybindings}
        provisionv3.get_volume_dict_from_job = (
            mock.Mock(return_value=volumeDict))
        result = provisionv3.extend_volume_in_SG(conn, storageConfigService,
                                                 theVolumeInstanceName,
                                                 inVolumeInstanceName,
                                                 volumeSize, extraSpecs)
        self.assertEqual(
            ({'classname': u'Symm_StorageVolume',
              'keybindings': {
                  'CreationClassName': u'Symm_StorageVolume',
                  'DeviceID': u'1',
                  'SystemCreationClassName': u'Symm_StorageSystem',
                  'SystemName': u'SYMMETRIX+000195900551'}}, 0), result)

    def test_extend_volume_in_SG_with_Exception(self):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        storageConfigService = {
            'CreationClassName': 'Symm_ElementCompositionService',
            'SystemName': 'SYMMETRIX+000195900551'}
        theVolumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        inVolumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeSize = 3

        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': True}
        job = {
            'Job': {'InstanceID': '9999', 'status': 'success', 'type': None}}
        conn.InvokeMethod = mock.Mock(return_value=(4096, job))
        provisionv3.utils.wait_for_job_complete = mock.Mock(return_value=(
            2, 'Failure'))
        self.assertRaises(
            exception.VolumeBackendAPIException,
            provisionv3.extend_volume_in_SG, conn, storageConfigService,
            theVolumeInstanceName, inVolumeInstanceName, volumeSize,
            extraSpecs)

    def test_create_volume_from_sg(self):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        storageConfigService = {
            'CreationClassName': 'EMC_StorageConfigurationService',
            'SystemName': 'SYMMETRIX+000195900551'}
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': True}
        volumeName = 'v3_vol'
        volumeSize = 3
        volumeDict, rc = (
            provisionv3.create_volume_from_sg(
                conn, storageConfigService, volumeName,
                self.data.default_sg_instance_name, volumeSize, extraSpecs))
        keybindings = volumeDict['keybindings']
        self.assertEqual('1', keybindings['DeviceID'])
        self.assertEqual(0, rc)

    @mock.patch.object(
        utils.VMAXUtils,
        'wait_for_job_complete',
        return_value=(-1, 'error'))
    def test_create_volume_from_sg_failed(self, mock_devices):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        storageConfigService = {
            'CreationClassName': 'EMC_StorageConfigurationService',
            'SystemName': 'SYMMETRIX+000195900551'}
        sgInstanceName = self.data.default_sg_instance_name
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': True}
        volumeName = 'failed_vol'
        volumeSize = 3
        self.assertRaises(
            exception.VolumeBackendAPIException,
            provisionv3.create_volume_from_sg,
            conn, storageConfigService, volumeName,
            sgInstanceName, volumeSize, extraSpecs)

    def test_create_storage_group_v3(self):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        controllerConfigService = {
            'CreationClassName': 'EMC_ControllerConfigurationService',
            'SystemName': 'SYMMETRIX+000195900551'}
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': True}
        groupName = self.data.storagegroupname
        srp = 'SRP_1'
        slo = 'Bronze'
        workload = 'DSS'
        provisionv3._find_new_storage_group = mock.Mock(
            return_value=self.data.default_sg_instance_name)
        newstoragegroup = provisionv3.create_storage_group_v3(
            conn, controllerConfigService, groupName, srp, slo, workload,
            extraSpecs, False)
        self.assertEqual(self.data.default_sg_instance_name, newstoragegroup)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_v3_default_sg_instance_name',
        return_value=(None, None, VMAXCommonData.default_sg_instance_name))
    def test_create_element_replica(self, mock_sg):
        provisionv3 = self.driver.common.provisionv3
        conn = FakeEcomConnection()
        repServiceInstanceName = {
            'CreationClassName': 'repServiceInstanceName',
            'SystemName': 'SYMMETRIX+000195900551'}
        extraSpecs = {'volume_backend_name': 'GOLD_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:slo': 'SRP_1',
                      'storagetype:workload': 'SRP_1'}
        sourceInstance = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        syncType = 7
        cloneName = 'new_ss'
        rc, job = provisionv3.create_element_replica(
            conn, repServiceInstanceName, cloneName, syncType, sourceInstance,
            extraSpecs)
        self.assertEqual(0, rc)


class VMAXMaskingTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXMaskingTest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'MaskingTests'
        configuration.config_group = 'MaskingTests'
        common.VMAXCommon._get_ecom_connection = mock.Mock(
            return_value=self.fake_ecom_connection())
        common.VMAXCommon._gather_info = mock.Mock(
            return_value=self.fake_gather_info())
        instancename = FakeCIMInstanceName()
        utils.VMAXUtils.get_instance_name = (
            instancename.fake_getinstancename)
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    def fake_ecom_connection(self):
        conn = FakeEcomConnection()
        return conn

    def fake_gather_info(self):
        return

    def test_get_v3_default_storage_group_instance_name(self):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        extraSpecs = self.data.extra_specs
        masking._get_and_remove_from_storage_group_v3 = mock.Mock()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        maskingviewdict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        result = (
            masking._get_v3_default_storagegroup_instancename(
                conn, maskingviewdict['volumeInstance'],
                maskingviewdict,
                controllerConfigService, maskingviewdict['volumeName']))
        self.assertEqual('OS-SRP_1-Bronze-DSS-SG', result['ElementName'])

    def test_get_v3_default_storage_group_instance_name_warning(self):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        extraSpecs = self.data.extra_specs
        masking.utils.get_storage_groups_from_volume = mock.Mock(
            return_value=[])
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        maskingviewdict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        result = (
            masking._get_v3_default_storagegroup_instancename(
                conn, maskingviewdict['volumeInstance'],
                maskingviewdict,
                controllerConfigService, maskingviewdict['volumeName']))
        self.assertIsNone(result)

    def test_return_volume_to_default_storage_group_v3(self):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        volumeName = "V3-Vol"
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        masking.provisionv3.create_storage_group_v3 = mock.Mock(
            return_value={'Value'})
        masking._is_volume_in_storage_group = mock.Mock(
            return_value=True)
        masking.return_volume_to_default_storage_group_v3 = mock.Mock()
        masking._return_back_to_default_sg(
            conn, controllerConfigService, volumeInstance, volumeName,
            extraSpecs)
        masking.return_volume_to_default_storage_group_v3.assert_called_with(
            conn, controllerConfigService,
            volumeInstance, volumeName, extraSpecs)

    def test_return_volume_to_default_storage_group_v3_exception(self):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        volumeName = "V3-Vol"
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))

        self.assertRaises(
            exception.VolumeBackendAPIException,
            masking.return_volume_to_default_storage_group_v3,
            conn, controllerConfigService,
            volumeInstance, volumeName, extraSpecs)

    def test_add_volume_to_sg_and_verify(self):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        volumeName = "V3-Vol"
        storageGroupInstanceName = self.data.storagegroups[0]
        sgGroupName = self.data.storagegroupname
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        msg = masking._add_volume_to_sg_and_verify(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstance, volumeName, sgGroupName, extraSpecs)
        self.assertIsNone(msg)

    def test_cleanup_deletion_v3(self):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        storageGroupInstanceName = self.data.storagegroups[1]
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        masking._remove_volume_from_sg = mock.Mock()
        masking._cleanup_deletion_v3(
            conn, controllerConfigService, volumeInstance, extraSpecs)
        masking._remove_volume_from_sg.assert_called_with(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstance, extraSpecs)

    # Bug 1552426 - failed rollback on V3 when MV issue
    def test_check_ig_rollback(self):
        # called on masking view rollback
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        connector = self.data.connector
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'slo': 'Bronze',
                      'pool': 'SRP_1',
                      }
        igGroupName = self.data.initiatorgroup_name
        host = igGroupName.split("-")[1]
        igInstance = masking._find_initiator_masking_group(
            conn, controllerConfigService, self.data.initiatorNames)
        # path 1: The masking view creation process created a now stale
        # initiator group before it failed.
        with mock.patch.object(masking,
                               '_last_volume_delete_initiator_group'):
            masking._check_ig_rollback(conn, controllerConfigService,
                                       igGroupName, connector, extraSpecs)
            (masking._last_volume_delete_initiator_group.
                assert_called_once_with(conn, controllerConfigService,
                                        igInstance, extraSpecs, host))
            # path 2: No initiator group was created before the masking
            # view process failed.
            with mock.patch.object(masking,
                                   '_find_initiator_masking_group',
                                   return_value=None):
                masking._last_volume_delete_initiator_group.reset_mock()
                masking._check_ig_rollback(conn, controllerConfigService,
                                           igGroupName, connector, extraSpecs)
                (masking._last_volume_delete_initiator_group.
                 assert_not_called())

    @mock.patch.object(
        masking.VMAXMasking,
        'get_associated_masking_groups_from_device',
        return_value=VMAXCommonData.storagegroups)
    @mock.patch.object(
        masking.VMAXMasking,
        'return_volume_to_default_storage_group_v3',
        return_value='Returning volume to default sg')
    def test_check_if_rollback_action_required_v3(
            self, mock_return, mock_group):
        conn = self.fake_ecom_connection()
        masking = self.driver.common.masking
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        extraSpecs_v3 = {'volume_backend_name': 'V3_BE',
                         'isV3': True,
                         'slo': 'Bronze',
                         'pool': 'SRP_1',
                         'connector': self.data.connector}

        vol = EMC_StorageVolume()
        vol['name'] = self.data.test_volume['name']
        vol['CreationClassName'] = 'Symm_StorageVolume'
        vol['ElementName'] = self.data.test_volume['id']
        vol['DeviceID'] = self.data.test_volume['device_id']
        vol['Id'] = self.data.test_volume['id']
        vol['SystemName'] = self.data.storage_system
        vol['NumberOfBlocks'] = self.data.test_volume['NumberOfBlocks']
        vol['BlockSize'] = self.data.test_volume['BlockSize']

        # Added vol to vol.path
        vol['SystemCreationClassName'] = 'Symm_StorageSystem'
        vol.path = vol
        vol.path.classname = vol['CreationClassName']
        rollbackDict = {}
        rollbackDict['isV3'] = True
        rollbackDict['defaultStorageGroupInstanceName'] = (
            self.data.default_storage_group)
        rollbackDict['sgGroupName'] = self.data.storagegroupname
        rollbackDict['sgName'] = self.data.storagegroupname
        rollbackDict['volumeName'] = 'vol1'
        rollbackDict['slo'] = 'Bronze'
        rollbackDict['volumeInstance'] = vol
        rollbackDict['controllerConfigService'] = controllerConfigService
        rollbackDict['extraSpecs'] = extraSpecs_v3
        rollbackDict['igGroupName'] = self.data.initiatorgroup_name
        rollbackDict['connector'] = self.data.connector
        # v3 Path 1 - The volume is in another storage group that isn't the
        # default storage group
        expectedmessage = (_("Rollback - Volume in another storage "
                             "group besides default storage group."))
        message = (
            masking.
            _check_if_rollback_action_for_masking_required(conn,
                                                           rollbackDict))
        self.assertEqual(expectedmessage, message)
        # v3 Path 2 - The volume is not in any storage group
        rollbackDict['sgGroupName'] = 'sq_not_exist'
        (rollbackDict
         ['defaultStorageGroupInstanceName']) = (self.data.
                                                 default_sg_instance_name)
        expectedmessage = (_("V3 rollback"))
        message = (
            masking.
            _check_if_rollback_action_for_masking_required(conn,
                                                           rollbackDict))
        self.assertEqual(expectedmessage, message)

    def test_remove_volume_from_sg(self):
        extraSpecs = self.data.extra_specs
        conn = self.fake_ecom_connection()
        common = self.driver.common
        masking = common.masking
        controllerConfigService = (
            common.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        storageGroupName = self.data.storagegroupname
        storageGroupInstanceName = (
            self.driver.utils.find_storage_masking_group(
                conn, controllerConfigService, storageGroupName))
        volumeInstanceNames = (
            conn.EnumerateInstanceNames("EMC_StorageVolume"))
        volumeInstanceName = volumeInstanceNames[0]
        volumeInstance = conn.GetInstance(volumeInstanceName)
        masking.get_devices_from_storage_group = (
            mock.Mock(return_value=volumeInstanceNames))
        masking._remove_volume_from_sg(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstance, extraSpecs)
        masking.get_devices_from_storage_group.assert_called_with(
            conn, storageGroupInstanceName)

    # bug 1555728: _create_initiator_Group uses multiple CIM calls
    # where one suffices
    def test_create_initiator_group(self):
        utils = self.driver.common.utils
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        controllerConfigService = (utils.
                                   find_controller_configuration_service(
                                       conn, self.data.storage_system))
        igGroupName = self.data.initiatorgroup_name
        hardwareIdinstanceNames = self.data.initiatorNames
        extraSpecs = self.data.extra_specs
        # path 1: Initiator Group created successfully
        foundInitiatorGroupName = (masking._create_initiator_Group(
                                   conn, controllerConfigService,
                                   igGroupName, hardwareIdinstanceNames,
                                   extraSpecs))
        self.assertEqual(foundInitiatorGroupName, igGroupName)
        # path 2: Unsuccessful Initiator Group creation
        with mock.patch.object(utils, 'wait_for_job_complete',
                               return_value=(10, None)):
            igGroupName = 'IG_unsuccessful'
            self.assertRaises(exception.VolumeBackendAPIException,
                              masking._create_initiator_Group,
                              conn, controllerConfigService,
                              igGroupName, hardwareIdinstanceNames,
                              extraSpecs)

    @mock.patch.object(
        masking.VMAXMasking,
        "_delete_initiators_from_initiator_group")
    @mock.patch.object(
        masking.VMAXMasking,
        "_delete_initiator_group")
    @mock.patch.object(
        masking.VMAXMasking,
        "_create_initiator_Group",
        return_value=VMAXCommonData.initiatorgroup_name)
    # bug 1579934: duplicate IG name error from SMI-S
    def test_verify_initiator_group_from_masking_view(
            self, create_ig, delete_ig, delete_initiators):
        utils = self.driver.common.utils
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        controllerConfigService = (
            utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        connector = self.data.connector
        maskingViewName = self.data.lunmaskctrl_name
        storageSystemName = self.data.storage_system
        igGroupName = self.data.initiatorgroup_name
        extraSpecs = self.data.extra_specs
        initiatorNames = (
            self.driver.common.masking._find_initiator_names(conn, connector))
        storageHardwareIDInstanceNames = (
            masking._get_storage_hardware_id_instance_names(
                conn, initiatorNames, storageSystemName))
        foundInitiatorGroupFromMaskingView = (
            masking._get_initiator_group_from_masking_view(
                conn, maskingViewName, storageSystemName))
        # path 1: initiator group from masking view matches initiator
        # group from connector
        verify = masking._verify_initiator_group_from_masking_view(
            conn, controllerConfigService, maskingViewName, connector,
            storageSystemName, igGroupName, extraSpecs)
        masking._create_initiator_Group.assert_not_called()
        self.assertTrue(verify)
        # path 2: initiator group from masking view does not match
        # initiator group from connector
        with mock.patch.object(
                masking, "_find_initiator_masking_group",
                return_value="not_a_match"):
            # path 2a: initiator group from connector is not None
            # - no new initiator group created
            verify = masking._verify_initiator_group_from_masking_view(
                conn, controllerConfigService, maskingViewName,
                connector, storageSystemName, igGroupName,
                extraSpecs)
            self.assertTrue(verify)
            masking._create_initiator_Group.assert_not_called()
            # path 2b: initiator group from connector is None
            # - new initiator group created
            with mock.patch.object(
                    masking, "_find_initiator_masking_group",
                    return_value=None):
                masking._verify_initiator_group_from_masking_view(
                    conn, controllerConfigService, maskingViewName,
                    connector, storageSystemName, igGroupName,
                    extraSpecs)
                (masking._create_initiator_Group.
                 assert_called_once_with(conn, controllerConfigService,
                                         igGroupName,
                                         storageHardwareIDInstanceNames,
                                         extraSpecs))
                # path 2b(i) - the name of the initiator group from the
                # masking view is the same as the provided igGroupName
                # - existing ig must be deleted
                (masking._delete_initiator_group.
                 assert_called_once_with(conn, controllerConfigService,
                                         foundInitiatorGroupFromMaskingView,
                                         igGroupName, extraSpecs))
                # path 2b(ii) - the name of the ig from the masking view
                # is different - do not delete the existing ig
                masking._delete_initiator_group.reset_mock()
                with mock.patch.object(
                        conn, "GetInstance",
                        return_value={'ElementName': "different_name"}):
                    masking._verify_initiator_group_from_masking_view(
                        conn, controllerConfigService, maskingViewName,
                        connector, storageSystemName, igGroupName,
                        extraSpecs)
                    masking._delete_initiator_group.assert_not_called()
            # path 3 - the masking view cannot be verified
            with mock.patch.object(
                    masking, "_get_storage_group_from_masking_view",
                    return_value=None):
                verify = masking._verify_initiator_group_from_masking_view(
                    conn, controllerConfigService, maskingViewName,
                    connector, storageSystemName, igGroupName,
                    extraSpecs)
                self.assertFalse(verify)

    @mock.patch.object(
        masking.VMAXMasking,
        "_check_adding_volume_to_storage_group",
        return_value=None)
    @mock.patch.object(
        masking.VMAXMasking,
        "_validate_masking_view",
        return_value=("mv_instance", VMAXCommonData.sg_instance_name, None))
    @mock.patch.object(
        masking.VMAXMasking,
        "_get_and_remove_from_storage_group_v3")
    @mock.patch.object(
        masking.VMAXMasking,
        '_check_if_rollback_action_for_masking_required')
    def test_get_or_create_masking_view_and_map_lun(self, check_rb, rm_sg,
                                                    validate_mv, check_sg):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        masking = common.masking
        connector = self.data.connector
        extraSpecs = self.data.extra_specs
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                common.conn, self.data.storage_system))
        defaultStorageGroupInstanceName = (
            {'CreationClassName': 'CIM_DeviceMaskingGroup',
             'ElementName': 'OS-SRP_1-Bronze-DSS-SG'})
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)
        with mock.patch.object(common, '_find_lun',
                               return_value=volumeInstance):
            maskingViewDict = common._populate_masking_dict(
                self.data.test_volume_v3, connector, extraSpecs)
        maskingViewDict['isLiveMigration'] = False
        rollbackDict = {}
        rollbackDict['controllerConfigService'] = controllerConfigService
        rollbackDict['defaultStorageGroupInstanceName'] = (
            defaultStorageGroupInstanceName)
        rollbackDict['volumeInstance'] = volumeInstance
        rollbackDict['volumeName'] = self.data.test_volume_v3['name']
        rollbackDict['fastPolicyName'] = None
        rollbackDict['isV3'] = True
        rollbackDict['extraSpecs'] = extraSpecs
        rollbackDict['sgGroupName'] = 'OS-fakehost-SRP_1-Bronze-DSS-I-SG'
        rollbackDict['igGroupName'] = self.data.initiatorgroup_name
        rollbackDict['pgGroupName'] = self.data.port_group
        rollbackDict['connector'] = self.data.connector
        # path 1: masking view creation or retrieval is successful
        with mock.patch.object(masking, "_get_port_group_name_from_mv",
                               return_value=(self.data.port_group, None)):
            deviceDict = masking.get_or_create_masking_view_and_map_lun(
                common.conn, maskingViewDict, extraSpecs)
            (masking._check_if_rollback_action_for_masking_required.
             assert_not_called())
            self.assertEqual(rollbackDict, deviceDict)
        # path 2: masking view creation or retrieval is unsuccessful
        with mock.patch.object(masking, "_get_port_group_name_from_mv",
                               return_value=(None, "error_message")):
            rollbackDict['storageSystemName'] = self.data.storage_system
            rollbackDict['slo'] = u'Bronze'
            self.assertRaises(exception.VolumeBackendAPIException,
                              masking.get_or_create_masking_view_and_map_lun,
                              common.conn, maskingViewDict, extraSpecs)

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_storage_group_from_masking_view_instance',
        return_value=VMAXCommonData.sg_instance_name)
    def test_check_existing_storage_group(self, mock_sg_from_mv):
        common = self.driver.common
        conn = self.fake_ecom_connection()
        mv_instance_name = {'CreationClassName': 'Symm_LunMaskingView',
                            'ElementName': 'OS-fakehost-gold-I-MV'}
        masking = common.masking
        sgFromMvInstanceName, msg = (
            masking._check_existing_storage_group(conn, mv_instance_name))
        self.assertEqual(VMAXCommonData.sg_instance_name,
                         sgFromMvInstanceName)
        self.assertIsNone(msg)

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_storage_group_from_masking_view_instance',
        return_value=None)
    def test_check_existing_storage_group_none(self, mock_sg_from_mv):
        common = self.driver.common
        conn = self.fake_ecom_connection()
        mv_instance_name = {'CreationClassName': 'Symm_LunMaskingView',
                            'ElementName': 'OS-fakehost-gold-I-MV'}
        masking = common.masking
        sgFromMvInstanceName, msg = (
            masking._check_existing_storage_group(conn, mv_instance_name))
        self.assertIsNone(sgFromMvInstanceName)
        self.assertIsNotNone(msg)

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_port_group_from_masking_view',
        return_value=VMAXCommonData.port_group)
    def test_get_port_group_name_from_mv_success(self, mock_pg_name):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        mv_name = self.data.lunmaskctrl_name
        system_name = self.data.storage_system

        conn.GetInstance = mock.Mock(
            return_value=self.data.port_group_instance)
        pg_name, err_msg = (
            masking._get_port_group_name_from_mv(conn, mv_name, system_name))

        self.assertIsNone(err_msg)
        self.assertIsNotNone(pg_name)

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_port_group_from_masking_view',
        return_value=None)
    def test_get_port_group_name_from_mv_fail_1(self, mock_pg_name):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        mv_name = self.data.lunmaskctrl_name
        system_name = self.data.storage_system

        pg_name, err_msg = (
            masking._get_port_group_name_from_mv(conn, mv_name, system_name))

        self.assertIsNone(pg_name)
        self.assertIsNotNone(err_msg)

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_port_group_from_masking_view',
        return_value=VMAXCommonData.port_group)
    def test_get_port_group_name_from_mv_fail_2(self, mock_pg_name):
        masking = self.driver.common.masking
        conn = self.fake_ecom_connection()
        mv_name = self.data.lunmaskctrl_name
        system_name = self.data.storage_system

        conn.GetInstance = mock.Mock(return_value={})
        pg_name, err_msg = (
            masking._get_port_group_name_from_mv(conn, mv_name, system_name))

        self.assertIsNone(pg_name)
        self.assertIsNotNone(err_msg)


class VMAXFCTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXFCTest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'FCTests'
        configuration.config_group = 'FCTests'
        common.VMAXCommon._gather_info = mock.Mock()
        common.VMAXCommon._get_ecom_connection = mock.Mock(
            return_value=FakeEcomConnection())
        driver = fc.VMAXFCDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver

    def test_terminate_connection_ig_present(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        common._unmap_lun = mock.Mock()
        common.get_masking_view_by_volume = mock.Mock(
            return_value='testMV')
        common.get_masking_views_by_port_group = mock.Mock(
            return_value=[])
        common.get_target_wwns_list = mock.Mock(
            return_value=VMAXCommonData.target_wwns)
        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))
        with mock.patch.object(self.driver.common,
                               'check_ig_instance_name',
                               return_value=initiatorGroupInstanceName):
            data = self.driver.terminate_connection(self.data.test_volume_v3,
                                                    self.data.connector)
        common.get_target_wwns_list.assert_called_once_with(
            VMAXCommonData.storage_system, self.data.test_volume_v3,
            VMAXCommonData.connector)
        numTargetWwns = len(VMAXCommonData.target_wwns)
        self.assertEqual(numTargetWwns, len(data['data']))

    @mock.patch.object(
        common.VMAXCommon,
        'check_ig_instance_name',
        return_value=None)
    @mock.patch.object(
        common.VMAXCommon,
        'get_target_wwns_list',
        return_value=VMAXCommonData.target_wwns)
    @mock.patch.object(
        common.VMAXCommon,
        'get_masking_views_by_port_group',
        return_value=[])
    @mock.patch.object(
        common.VMAXCommon,
        'get_masking_view_by_volume',
        return_value='testMV')
    @mock.patch.object(
        common.VMAXCommon,
        '_unmap_lun')
    def test_terminate_connection_no_ig(self, mock_unmap,
                                        mock_mv_vol, mock_mv_pg,
                                        mock_wwns, mock_check_ig):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        data = self.driver.terminate_connection(self.data.test_volume_v3,
                                                self.data.connector)
        common.get_target_wwns_list.assert_called_once_with(
            VMAXCommonData.storage_system, self.data.test_volume_v3,
            VMAXCommonData.connector)
        numTargetWwns = len(VMAXCommonData.target_wwns)
        self.assertEqual(numTargetWwns, len(data['data']))

    def test_get_common_masking_views_two_exist(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        maskingviews = [{'CreationClassName': 'Symm_LunMaskingView',
                         'ElementName': 'MV1'},
                        {'CreationClassName': 'Symm_LunMaskingView',
                         'ElementName': 'MV2'}]

        portGroupInstanceName = (
            self.driver.common.masking._get_port_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))

        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))
        common.get_masking_views_by_port_group = mock.Mock(
            return_value=maskingviews)
        common.get_masking_views_by_initiator_group = mock.Mock(
            return_value=maskingviews)

        mvInstances = self.driver._get_common_masking_views(
            portGroupInstanceName, initiatorGroupInstanceName)
        self.assertEqual(2, len(mvInstances))

    def test_get_common_masking_views_one_overlap(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        maskingviewsPG = [{'CreationClassName': 'Symm_LunMaskingView',
                           'ElementName': 'MV1'},
                          {'CreationClassName': 'Symm_LunMaskingView',
                           'ElementName': 'MV2'}]

        maskingviewsIG = [{'CreationClassName': 'Symm_LunMaskingView',
                           'ElementName': 'MV1'}]

        portGroupInstanceName = (
            self.driver.common.masking._get_port_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))

        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))
        common.get_masking_views_by_port_group = mock.Mock(
            return_value=maskingviewsPG)
        common.get_masking_views_by_initiator_group = mock.Mock(
            return_value=maskingviewsIG)

        mvInstances = self.driver._get_common_masking_views(
            portGroupInstanceName, initiatorGroupInstanceName)
        self.assertEqual(1, len(mvInstances))

    def test_get_common_masking_views_no_overlap(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        maskingviewsPG = [{'CreationClassName': 'Symm_LunMaskingView',
                           'ElementName': 'MV2'}]

        maskingviewsIG = [{'CreationClassName': 'Symm_LunMaskingView',
                           'ElementName': 'MV1'}]

        portGroupInstanceName = (
            self.driver.common.masking._get_port_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))

        initiatorGroupInstanceName = (
            self.driver.common.masking._get_initiator_group_from_masking_view(
                common.conn, self.data.lunmaskctrl_name,
                self.data.storage_system))
        common.get_masking_views_by_port_group = mock.Mock(
            return_value=maskingviewsPG)
        common.get_masking_views_by_initiator_group = mock.Mock(
            return_value=maskingviewsIG)

        mvInstances = self.driver._get_common_masking_views(
            portGroupInstanceName, initiatorGroupInstanceName)
        self.assertEqual(0, len(mvInstances))

    @mock.patch.object(
        common.VMAXCommon,
        'initialize_connection',
        return_value=VMAXCommonData.fc_device_info)
    @mock.patch.object(
        fc.VMAXFCDriver,
        '_build_initiator_target_map',
        return_value=(VMAXCommonData.target_wwns,
                      VMAXCommonData.end_point_map))
    def test_initialize_connection_snapshot(self, mock_map, mock_conn):
        data = self.driver.initialize_connection_snapshot(
            self.data.test_snapshot_v3, self.data.connector)
        self.assertEqual('fibre_channel', data['driver_volume_type'])
        self.assertEqual(3, data['data']['target_lun'])

    @mock.patch.object(
        common.VMAXCommon,
        '_unmap_lun')
    @mock.patch.object(
        fc.VMAXFCDriver,
        '_get_zoning_mappings',
        return_value=(VMAXCommonData.zoning_mappings))
    @mock.patch.object(
        common.VMAXCommon,
        'check_ig_instance_name',
        return_value=None)
    def test_terminate_connection_snapshot(
            self, mock_check_ig, mock_zoning_map, mock_unmap):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        data = self.driver.terminate_connection_snapshot(
            self.data.test_snapshot_v3, self.data.connector)
        self.assertEqual('fibre_channel', data['driver_volume_type'])
        self.assertEqual(2, len(data['data']['target_wwn']))

    @mock.patch.object(
        provision.VMAXProvision,
        'remove_device_from_storage_group')
    def test_remove_device_from_storage_group(self, mock_remove):
        conn = FakeEcomConnection()
        common = self.driver.common
        controllerConfigService = (
            common.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeName = 'vol1'
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        masking = common.masking
        volumeInstance = conn.GetInstance(volumeInstanceName)
        storageGroupName = self.data.storagegroupname
        storageGroupInstanceName = (
            common.utils.find_storage_masking_group(
                conn, controllerConfigService, storageGroupName))
        masking.remove_device_from_storage_group(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstance, volumeName, storageGroupName, extraSpecs)
        masking.provision.remove_device_from_storage_group.assert_called_with(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstanceName, volumeName, extraSpecs)


@ddt.ddt
class VMAXUtilsTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXUtilsTest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'UtilsTests'
        configuration.config_group = 'UtilsTests'
        common.VMAXCommon._gather_info = mock.Mock()
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    def test_set_target_element_supplier_in_rsd(self):
        conn = FakeEcomConnection()
        extraSpecs = self.data.extra_specs
        repServiceInstanceName = (
            self.driver.utils.find_replication_service(
                conn, self.data.storage_system))
        rsdInstance = self.driver.utils.set_target_element_supplier_in_rsd(
            conn, repServiceInstanceName,
            common.SNAPVX_REPLICATION_TYPE,
            common.CREATE_NEW_TARGET, extraSpecs)
        self.assertIsNotNone(rsdInstance)

    def test_set_copy_methodology_in_rsd(self):
        conn = FakeEcomConnection()
        extraSpecs = self.data.extra_specs
        repServiceInstanceName = (
            self.driver.utils.find_replication_service(
                conn, self.data.storage_system))
        rsdInstance = self.driver.utils.set_copy_methodology_in_rsd(
            conn, repServiceInstanceName,
            provision.SYNC_CLONE_LOCAL,
            provision.COPY_ON_WRITE, extraSpecs)
        self.assertIsNotNone(rsdInstance)

    def getinstance_capability(self, reptypes):
        repservicecap = CIM_ReplicationServiceCapabilities()
        repservicecap['CreationClassName'] = (
            'CIM_ReplicationServiceCapabilities')

        classcimproperty = Fake_CIMProperty()
        supportedReplicationTypes = (
            classcimproperty.fake_getSupportedReplicationTypesCIMProperty(
                reptypes))
        properties = {u'SupportedReplicationTypes': supportedReplicationTypes}
        repservicecap.properties = properties
        return repservicecap

    @ddt.data(('V3', True), ('V3_ASYNC', True), ('V3_SYNC', True),
              ('V2', False))
    @ddt.unpack
    def test_is_clone_licensed(self, reptypes, isV3):
        conn = FakeEcomConnection()
        capabilityInstanceName = self.getinstance_capability(reptypes)
        conn.GetInstance = mock.Mock(
            return_value=capabilityInstanceName)
        self.assertTrue(self.driver.utils.is_clone_licensed(
            conn, capabilityInstanceName, isV3))

    def test_is_clone_licensed_false(self):
        conn = FakeEcomConnection()
        isV3 = True
        reptypes = None
        capabilityInstanceName = self.getinstance_capability(reptypes)
        conn.GetInstance = mock.Mock(
            return_value=capabilityInstanceName)
        self.assertFalse(self.driver.utils.is_clone_licensed(
            conn, capabilityInstanceName, isV3))

    def test_get_pool_capacities(self):
        conn = FakeEcomConnection()

        (total_capacity_gb, free_capacity_gb, provisioned_capacity_gb,
         array_max_over_subscription) = (
            self.driver.utils.get_pool_capacities(
                conn, self.data.poolname, self.data.storage_system))
        self.assertEqual(931, total_capacity_gb)
        self.assertEqual(465, free_capacity_gb)
        self.assertEqual(465, provisioned_capacity_gb)
        self.assertEqual(1.5, array_max_over_subscription)

    def test_get_pool_capacities_none_array_max_oversubscription(self):
        conn = FakeEcomConnection()
        null_emcmaxsubscriptionpercent = {
            'TotalManagedSpace': '1000000000000',
            'ElementName': 'gold',
            'RemainingManagedSpace': '500000000000',
            'SystemName': 'SYMMETRIX+000195900551',
            'CreationClassName': 'Symm_VirtualProvisioningPool',
            'EMCSubscribedCapacity': '500000000000'}
        conn.GetInstance = mock.Mock(
            return_value=null_emcmaxsubscriptionpercent)
        (total_capacity_gb, free_capacity_gb, provisioned_capacity_gb,
         array_max_over_subscription) = (
            self.driver.utils.get_pool_capacities(
                conn, self.data.poolname, self.data.storage_system))
        self.assertEqual(65534, array_max_over_subscription)

    def test_get_ratio_from_max_sub_per(self):
        max_subscription_percent_float = (
            self.driver.utils.get_ratio_from_max_sub_per(150))
        self.assertEqual(1.5, max_subscription_percent_float)

    def test_get_ratio_from_max_sub_per_none_value(self):
        max_subscription_percent_float = (
            self.driver.utils.get_ratio_from_max_sub_per(str(0)))
        self.assertIsNone(max_subscription_percent_float)

    def test_update_storage_QOS(self):
        conn = FakeEcomConnection()
        pywbem = mock.Mock()
        pywbem.cim_obj = mock.Mock()
        pywbem.cim_obj.CIMInstance = mock.Mock()
        utils.pywbem = pywbem

        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'qos': {
                          'maxIOPS': '6000',
                          'maxMBPS': '6000',
                          'DistributionType': 'Always'
                      }}

        storageGroupInstanceName = {
            'CreationClassName': 'CIM_DeviceMaskingGroup',
            'EMCMaximumIO': 6000,
            'EMCMaximumBandwidth': 5000,
            'EMCMaxIODynamicDistributionType': 1

        }
        modifiedstorageGroupInstance = {
            'CreationClassName': 'CIM_DeviceMaskingGroup',
            'EMCMaximumIO': 6000,
            'EMCMaximumBandwidth': 6000,
            'EMCMaxIODynamicDistributionType': 1

        }
        conn.ModifyInstance = (
            mock.Mock(return_value=modifiedstorageGroupInstance))
        self.driver.common.utils.update_storagegroup_qos(
            conn, storageGroupInstanceName, extraSpecs)

        modifiedInstance = self.driver.common.utils.update_storagegroup_qos(
            conn, storageGroupInstanceName, extraSpecs)
        self.assertIsNotNone(modifiedInstance)
        self.assertEqual(
            6000, modifiedInstance['EMCMaximumIO'])
        self.assertEqual(
            6000, modifiedInstance['EMCMaximumBandwidth'])
        self.assertEqual(
            1, modifiedInstance['EMCMaxIODynamicDistributionType'])
        self.assertEqual('CIM_DeviceMaskingGroup',
                         modifiedInstance['CreationClassName'])

    def test_get_iqn(self):
        conn = FakeEcomConnection()
        iqn = "iqn.1992-04.com.emc:600009700bca30c01b9c012000000003,t,0x0001"
        ipprotocolendpoints = conn._enum_ipprotocolendpoint()
        foundIqn = self.driver.utils.get_iqn(conn, ipprotocolendpoints[1])
        self.assertEqual(iqn, foundIqn)

    # bug #1605193 - Cleanup of Initiator Group fails
    def test_check_ig_instance_name_present(self):
        conn = FakeEcomConnection()
        initiatorgroup = SE_InitiatorMaskingGroup()
        initiatorgroup['CreationClassName'] = (
            self.data.initiatorgroup_creationclass)
        initiatorgroup['DeviceID'] = self.data.initiatorgroup_id
        initiatorgroup['SystemName'] = self.data.storage_system
        initiatorgroup['ElementName'] = self.data.initiatorgroup_name
        foundIg = self.driver.utils.check_ig_instance_name(
            conn, initiatorgroup)
        self.assertEqual(initiatorgroup, foundIg)

    # bug #1605193 - Cleanup of Initiator Group fails
    def test_check_ig_instance_name_not_present(self):
        conn = FakeEcomConnection()
        initiatorgroup = None
        with mock.patch.object(self.driver.utils,
                               'get_existing_instance',
                               return_value=None):
            foundIg = self.driver.utils.check_ig_instance_name(
                conn, initiatorgroup)
            self.assertIsNone(foundIg)

    @mock.patch.object(
        utils.VMAXUtils,
        '_is_sync_complete',
        return_value=False)
    def test_is_sync_complete(self, mock_sync):
        conn = FakeEcomConnection()
        syncname = SE_ConcreteJob()
        syncname.classname = 'SE_StorageSynchronized_SV_SV'
        syncname['CopyState'] = self.data.UNSYNCHRONIZED
        issynched = self.driver.common.utils._is_sync_complete(conn, syncname)
        self.assertFalse(issynched)

    def test_get_v3_storage_group_name_compression_disabled(self):
        poolName = 'SRP_1'
        slo = 'Diamond'
        workload = 'DSS'
        isCompressionDisabled = True
        storageGroupName = self.driver.utils.get_v3_storage_group_name(
            poolName, slo, workload, isCompressionDisabled)
        self.assertEqual("OS-SRP_1-Diamond-DSS-CD-SG", storageGroupName)

    @mock.patch.object(
        utils.VMAXUtils,
        'get_smi_version',
        return_value=831)
    def test_is_all_flash(self, mock_version):
        conn = FakeEcomConnection()
        array = '000197200056'
        self.assertTrue(self.driver.utils.is_all_flash(conn, array))

    def test_find_sync_sv_sv(self):
        conn = FakeEcomConnection()
        storageSystem = self.data.storage_system
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        extraSpecs = self.data.extra_specs
        syncInstance = (conn.ReferenceNames(
            volumeInstance.path,
            ResultClass='SE_StorageSynchronized_SV_SV'))[0]
        foundSyncInstance = self.driver.utils.find_sync_sv_by_volume(
            conn, storageSystem, volumeInstance, extraSpecs)
        self.assertEqual(syncInstance, foundSyncInstance)

    def test_get_assoc_v2_pool_from_vol(self):
        conn = FakeEcomConnection()
        volumeInstanceName = {'CreationClassName': "Symm_StorageVolume",
                              'DeviceID': "0123",
                              'SystemName': "12345"}

        pool = conn.AssociatorNames(
            volumeInstanceName, ResultClass='EMC_VirtualProvisioningPool')
        poolName = self.driver.utils.get_assoc_v2_pool_from_volume(
            conn, volumeInstanceName)

        self.assertEqual(pool[0]['ElementName'], poolName['ElementName'])

    def test_get_assoc_v2_pool_from_vol_fail(self):
        conn = FakeEcomConnection()
        volumeInstanceName = {'CreationClassName': "Symm_StorageVolume",
                              'DeviceID': "0123",
                              'SystemName': "12345"}

        conn.AssociatorNames = mock.Mock(return_value={})

        poolName = self.driver.utils.get_assoc_v2_pool_from_volume(
            conn, volumeInstanceName)

        self.assertIsNone(poolName)

    def test_get_assoc_v3_pool_from_vol(self):
        conn = FakeEcomConnection()
        volumeInstanceName = {'CreationClassName': "Symm_StorageVolume",
                              'DeviceID': "0123",
                              'SystemName': "12345"}

        pool = conn.AssociatorNames(
            volumeInstanceName, ResultClass='Symm_SRPStoragePool')
        poolName = self.driver.utils.get_assoc_v3_pool_from_volume(
            conn, volumeInstanceName)

        self.assertEqual(pool[0]['ElementName'], poolName['ElementName'])

    def test_get_assoc_v3_pool_from_vol_fail(self):
        conn = FakeEcomConnection()
        volumeInstanceName = {'CreationClassName': "Symm_StorageVolume",
                              'DeviceID': "0123",
                              'SystemName': "12345"}

        conn.AssociatorNames = mock.Mock(return_value={})

        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.utils.get_assoc_v3_pool_from_volume,
                          conn, volumeInstanceName)

    def test_check_volume_no_fast_fail(self):
        utils = self.driver.common.utils
        initial_setup = {'volume_backend_name': 'FCFAST',
                         'storagetype:fastpolicy': 'GOLD'}

        self.assertRaises(exception.VolumeBackendAPIException,
                          utils.check_volume_no_fast,
                          initial_setup)

    def test_check_volume_no_fast_pass(self):
        utils = self.driver.common.utils
        initial_setup = {'volume_backend_name': 'FCnoFAST',
                         'storagetype:fastpolicy': None}

        self.assertTrue(utils.check_volume_no_fast(
            initial_setup))

    def test_check_volume_not_in_masking_view_pass(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        bindings = {'CreationClassName': 'Symm_StorageVolume',
                    'SystemName': self.data.storage_system,
                    'DeviceID': self.data.test_volume['device_id'],
                    'SystemCreationClassName': 'Symm_StorageSystem'}
        inst = FakeCIMInstanceName()
        fake_inst = inst.fake_getinstancename('Symm_StorageVolume', bindings)

        sgInstanceNames = conn.AssociatorNames(fake_inst,
                                               ResultClass=
                                               'CIM_DeviceMaskingGroup')

        conn.AssociatorNames = mock.Mock(return_value={})

        mock.patch.object(self.driver.utils, 'get_storage_groups_from_volume',
                          return_value=sgInstanceNames)

        self.assertTrue(
            utils.check_volume_not_in_masking_view(
                conn, fake_inst, self.data.test_volume['device_id']))

    def test_check_volume_not_in_masking_view_fail(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        bindings = {'CreationClassName': 'Symm_StorageVolume',
                    'SystemName': self.data.storage_system,
                    'DeviceID': self.data.test_volume['device_id'],
                    'SystemCreationClassName': 'Symm_StorageSystem'}
        inst = FakeCIMInstanceName()
        fake_inst = inst.fake_getinstancename('Symm_StorageVolume', bindings)

        self.assertRaises(exception.VolumeBackendAPIException,
                          utils.check_volume_not_in_masking_view,
                          conn, fake_inst, self.data.test_volume['device_id'])

    def test_check_volume_not_replication_source_pass(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        self.assertTrue(
            utils.check_volume_not_replication_source(
                conn, self.data.storage_system_v3,
                self.data.test_volume['device_id']))

    def test_check_volume_not_replication_source_fail(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        replication_source = 'testReplicationSync'

        utils.get_associated_replication_from_source_volume = (
            mock.Mock(return_value=replication_source))

        self.assertRaises(
            exception.VolumeBackendAPIException,
            utils.check_volume_not_replication_source,
            conn, self.data.storage_system_v3,
            self.data.test_volume['device_id'])

    def test_check_is_volume_in_cinder_managed_pool_fail(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        volumeInstanceName = {'CreationClassName': "Symm_StorageVolume",
                              'DeviceID': "0123",
                              'SystemName': "12345"}

        poolInstanceName = {}
        poolInstanceName['InstanceID'] = "SATA_GOLD1"
        deviceId = '0123'

        self.assertRaises(
            exception.VolumeBackendAPIException,
            utils.check_is_volume_in_cinder_managed_pool,
            conn, volumeInstanceName, poolInstanceName, deviceId)

    def test_check_is_volume_in_cinder_managed_pool_pass(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        volumeInstanceName = {}
        poolInstanceName = {}
        poolInstanceName['InstanceID'] = "SATA_GOLD2"
        deviceId = self.data.test_volume['device_id']

        utils.get_assoc_v2_pool_from_volume = (
            mock.Mock(return_value=poolInstanceName))

        self.assertTrue(
            utils.check_is_volume_in_cinder_managed_pool(
                conn, volumeInstanceName, poolInstanceName, deviceId))

    def test_find_volume_by_device_id_on_array(self):
        conn = FakeEcomConnection()
        utils = self.driver.common.utils

        bindings = {'CreationClassName': 'Symm_StorageVolume',
                    'SystemName': self.data.storage_system,
                    'DeviceID': self.data.test_volume['device_id'],
                    'SystemCreationClassName': 'Symm_StorageSystem'}

        inst = FakeCIMInstanceName()
        fake_inst = inst.fake_getinstancename('Symm_StorageVolume', bindings)
        utils.find_volume_by_device_id_on_array = mock.Mock(
            return_value=fake_inst)

        volumeInstanceName = utils.find_volume_by_device_id_on_array(
            self.data.storage_system, self.data.test_volume['device_id'])

        expectVolume = {}
        expectVolume['CreationClassName'] = 'Symm_StorageVolume'
        expectVolume['DeviceID'] = self.data.test_volume['device_id']
        expect = conn.GetInstance(expectVolume)

        provider_location = ast.literal_eval(expect['provider_location'])
        bindings = provider_location['keybindings']

        self.assertEqual(bindings, volumeInstanceName)

    def test_get_array_and_device_id(self):
        utils = self.driver.common.utils
        volume = self.data.test_volume.copy()
        volume['volume_metadata'] = {'array': self.data.array_v3}
        external_ref = {u'source-name': u'00002'}
        array, device_id = utils.get_array_and_device_id(
            volume, external_ref)
        self.assertEqual(self.data.array_v3, array)
        self.assertEqual('00002', device_id)

    def test_get_array_and_device_id_exception(self):
        utils = self.driver.common.utils
        volume = self.data.test_volume.copy()
        volume['volume_metadata'] = {'array': self.data.array}
        external_ref = {u'source-name': None}
        self.assertRaises(exception.VolumeBackendAPIException,
                          utils.get_array_and_device_id, volume, external_ref)


class VMAXCommonTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXCommonTest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'CommonTests'
        configuration.config_group = 'CommonTests'
        common.VMAXCommon._gather_info = mock.Mock()
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils,
                         'find_controller_configuration_service',
                         return_value=None)
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_create_duplicate_volume(self, mock_pool):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        sourceInstance = common.conn.GetInstance(volumeInstanceName)
        cloneName = "SS-V3-Vol"
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        targetInstance = common.conn.GetInstance(volumeInstanceName)
        common.utils.find_volume_instance = mock.Mock(
            return_value=targetInstance)
        self.driver.common._get_or_create_storage_group_v3 = mock.Mock(
            return_value = self.data.default_sg_instance_name)
        duplicateVolumeInstance = self.driver.common._create_duplicate_volume(
            sourceInstance, cloneName, extraSpecs)
        self.assertIsNotNone(duplicateVolumeInstance)

    @mock.patch.object(
        common.VMAXCommon,
        'get_target_wwns_from_masking_view',
        return_value=["5000090000000000"])
    def test_get_target_wwn_list(self, mock_tw):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        targetWwns = common.get_target_wwns_list(
            VMAXCommonData.storage_system,
            VMAXCommonData.test_volume_v3, VMAXCommonData.connector)
        self.assertListEqual(["5000090000000000"], targetWwns)

    @mock.patch.object(
        common.VMAXCommon,
        'get_target_wwns_from_masking_view',
        return_value=[])
    def test_get_target_wwn_list_empty(self, mock_tw):
        common = self.driver.common
        common.conn = FakeEcomConnection()

        self.assertRaises(
            exception.VolumeBackendAPIException,
            common.get_target_wwns_list, VMAXCommonData.storage_system,
            VMAXCommonData.test_volume_v3, VMAXCommonData.connector)

    def test_cleanup_target(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        targetInstance = common.conn.GetInstance(volumeInstanceName)
        repServiceInstanceName = (
            self.driver.utils.find_replication_service(
                common.conn, self.data.storage_system))
        common.utils.find_sync_sv_by_volume = mock.Mock(
            return_value=(None, None))

        self.driver.common._cleanup_target(
            repServiceInstanceName, targetInstance, extraSpecs)

    def test_get_ip_and_iqn(self):
        conn = FakeEcomConnection()
        endpoint = {}
        ipprotocolendpoints = conn._enum_ipprotocolendpoint()
        ip_and_iqn = self.driver.common.get_ip_and_iqn(conn, endpoint,
                                                       ipprotocolendpoints[0])
        ip_and_iqn = self.driver.common.get_ip_and_iqn(conn, endpoint,
                                                       ipprotocolendpoints[1])
        self.assertEqual(
            'iqn.1992-04.com.emc:600009700bca30c01b9c012000000003,t,0x0001',
            ip_and_iqn['iqn'])
        self.assertEqual(
            '10.10.10.10', ip_and_iqn['ip'])

    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    def test_extend_volume(self, mock_compare):
        self.driver.common.conn = FakeEcomConnection()
        conn = FakeEcomConnection()
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = conn.GetInstance(volumeInstanceName)
        new_size_gb = 5
        old_size_gbs = 1
        volumeName = 'extendVol'
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'pool': 'SRP_1',
                      'workload': 'DSS',
                      'slo': 'Bronze'}
        self.driver.common._extend_volume(
            self.data.test_volume, volumeInstance, volumeName,
            new_size_gb, old_size_gbs, extraSpecs)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=(VMAXCommonData.extra_specs))
    def test_get_consistency_group_utils(self, mock_init, mock_pool):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        replicationService, storageSystem, extraSpecsList, isV3 = (
            common._get_consistency_group_utils(
                common.conn, VMAXCommonData.test_CG))
        self.assertEqual(
            self.data.extra_specs, extraSpecsList[0]['extraSpecs'])

        self.assertEqual(common.conn.EnumerateInstanceNames(
            'EMC_ReplicationService')[0], replicationService)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volumetype_extraspecs',
        return_value=(VMAXCommonData.multi_pool_extra_specs))
    def test_get_consistency_group_utils_multi_pool_enabled(
            self, mock_init, mock_pool):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        replicationService, storageSystem, extraSpecsList, isV3 = (
            common._get_consistency_group_utils(
                common.conn, VMAXCommonData.test_CG))
        self.assertEqual(
            self.data.multi_pool_extra_specs, extraSpecsList[0]['extraSpecs'])
        self.assertEqual(1, len(extraSpecsList))
        self.assertEqual(common.conn.EnumerateInstanceNames(
            'EMC_ReplicationService')[0], replicationService)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        utils.VMAXUtils,
        'get_volumetype_extraspecs',
        return_value=(VMAXCommonData.multi_pool_extra_specs))
    def test_get_consistency_group_utils_multi_pool_multi_vp(
            self, mock_init, mock_pool):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        test_CG_multi_vp = consistencygroup.ConsistencyGroup(
            context=None, name='myCG1', id=uuid.uuid1(),
            volume_type_id='abc,def',
            status=fields.ConsistencyGroupStatus.AVAILABLE)
        replicationService, storageSystem, extraSpecsList, isV3 = (
            common._get_consistency_group_utils(
                common.conn, test_CG_multi_vp))
        self.assertEqual(2, len(extraSpecsList))

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=(VMAXCommonData.extra_specs))
    def test_get_consistency_group_utils_single_pool_multi_vp(
            self, mock_init, mock_pool):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        test_CG_multi_vp = consistencygroup.ConsistencyGroup(
            context=None, name='myCG1', id=uuid.uuid1(),
            volume_type_id='abc,def',
            status=fields.ConsistencyGroupStatus.AVAILABLE)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            common._get_consistency_group_utils, common.conn,
            test_CG_multi_vp)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=(VMAXCommonData.extra_specs))
    def test_get_consistency_group_utils_single_pool_single_vp(
            self, mock_init, mock_pool):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        test_CG_single_vp = consistencygroup.ConsistencyGroup(
            context=None, name='myCG1', id=uuid.uuid1(),
            volume_type_id='abc,',
            status=fields.ConsistencyGroupStatus.AVAILABLE)
        replicationService, storageSystem, extraSpecsList, isV3 = (
            common._get_consistency_group_utils(
                common.conn, test_CG_single_vp))
        self.assertEqual(1, len(extraSpecsList))

    def test_update_consistency_group_name(self):
        common = self.driver.common
        cg_name = common._update_consistency_group_name(
            VMAXCommonData.test_CG)
        self.assertEqual('myCG1_%s' % fake_constants.UUID1,
                         cg_name)

    def test_update_consistency_group_name_truncate_name(self):
        common = self.driver.common
        test_cg = {'name': 'This_is_too_long_a_name_for_a_consistency_group',
                   'id': fake_constants.UUID1,
                   'volume_type_id': 'abc',
                   'status': fields.ConsistencyGroupStatus.AVAILABLE}
        cg_name = common._update_consistency_group_name(test_cg)
        self.assertEqual(
            'This_is_too_listency_group_%s' % fake_constants.UUID1,
            cg_name)

    # Bug 1401297: Cinder volumes can point at wrong backend vol
    def test_find_lun_check_element_name(self):
        common = self.driver.common
        volume = self.data.test_volume
        common.conn = FakeEcomConnection()
        # Path 1: Volume is retrieved successfully
        foundVolumeInstance = common._find_lun(volume)
        self.assertEqual(foundVolumeInstance['ElementName'],
                         volume['id'])
        # Path 2: Volume cannot be found
        deleted_vol = self.data.deleted_volume
        foundVolumeInstance = common._find_lun(deleted_vol)
        self.assertIsNone(foundVolumeInstance)

    def populate_masking_dict_setup(self):
        extraSpecs = {'storagetype:pool': u'gold_pool',
                      'volume_backend_name': 'GOLD_POOL_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': False,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:fastpolicy': u'GOLD'}
        return extraSpecs

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_fast(self, mock_find_lun):
        extraSpecs = self.populate_masking_dict_setup()
        # If fast is enabled it will uniquely determine the SG and MV
        # on the host along with the protocol(iSCSI) e.g. I
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-GOLD-FP-I-SG', maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-GOLD-FP-I-MV', maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_fast_more_than_14chars(self, mock_find_lun):
        # If the length of the FAST policy name is greater than 14 chars
        extraSpecs = self.populate_masking_dict_setup()
        extraSpecs['storagetype:fastpolicy'] = 'GOLD_MORE_THAN_FOURTEEN_CHARS'
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-GOLD_MO__CHARS-FP-I-SG',
            maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-GOLD_MO__CHARS-FP-I-MV',
            maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_no_fast(self, mock_find_lun):
        # If fast isn't enabled the pool will uniquely determine the SG and MV
        # on the host along with the protocol(iSCSI) e.g. I
        extraSpecs = self.populate_masking_dict_setup()
        extraSpecs['storagetype:fastpolicy'] = None
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-gold_pool-I-SG', maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-gold_pool-I-MV', maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_fast_both_exceeding(self, mock_find_lun):
        # If the length of the FAST policy name is greater than 14 chars and
        # the length of the short host is more than 38 characters
        extraSpecs = self.populate_masking_dict_setup()
        connector = {'host': 'SHORT_HOST_MORE_THEN THIRTY_EIGHT_CHARACTERS'}
        extraSpecs['storagetype:fastpolicy'] = (
            'GOLD_MORE_THAN_FOURTEEN_CHARACTERS')
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertLessEqual(len(maskingViewDict['sgGroupName']), 64)
        self.assertLessEqual(len(maskingViewDict['maskingViewName']), 64)

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_no_fast_both_exceeding(self, mock_find_lun):
        # If the length of the FAST policy name is greater than 14 chars and
        # the length of the short host is more than 38 characters
        extraSpecs = self.populate_masking_dict_setup()
        connector = {'host': 'SHORT_HOST_MORE_THEN THIRTY_EIGHT_CHARACTERS'}
        extraSpecs['storagetype:pool'] = (
            'GOLD_POOL_MORE_THAN_SIXTEEN_CHARACTERS')
        extraSpecs['storagetype:fastpolicy'] = None
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertLessEqual(len(maskingViewDict['sgGroupName']), 64)
        self.assertLessEqual(len(maskingViewDict['maskingViewName']), 64)

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_no_slo(self, mock_find_lun):
        extraSpecs = {'storagetype:pool': 'SRP_1',
                      'volume_backend_name': 'V3_BE',
                      'storagetype:workload': None,
                      'storagetype:slo': None,
                      'storagetype:array': '1234567891011',
                      'isV3': True,
                      'portgroupname': 'OS-portgroup-PG'}
        self.populate_masking_dict_setup()
        # If fast is enabled it will uniquely determine the SG and MV
        # on the host along with the protocol(iSCSI) e.g. I
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-No_SLO-I-SG', maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-No_SLO-I-MV', maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_slo_NONE(self, mock_find_lun):
        extraSpecs = {'storagetype:pool': 'SRP_1',
                      'volume_backend_name': 'V3_BE',
                      'storagetype:workload': 'NONE',
                      'storagetype:slo': 'NONE',
                      'storagetype:array': '1234567891011',
                      'isV3': True,
                      'portgroupname': 'OS-portgroup-PG'}
        self.populate_masking_dict_setup()
        # If fast is enabled it will uniquely determine the SG and MV
        # on the host along with the protocol(iSCSI) e.g. I
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, self.data.connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-SRP_1-NONE-NONE-I-SG', maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-SRP_1-NONE-NONE-I-MV',
            maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_v3(self, mock_find_lun):
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'VMAX_ISCSI_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS'}
        connector = {'host': 'fakehost'}
        self.populate_masking_dict_setup()
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertEqual('OS-fakehost-SRP_1-Diamond-DSS-I-SG',
                         maskingViewDict['sgGroupName'])
        self.assertEqual('OS-fakehost-SRP_1-Diamond-DSS-I-MV',
                         maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_v3_compression(self, mock_find_lun):
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'COMPRESSION_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS',
                      'storagetype:disablecompression': 'True'}
        connector = self.data.connector
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-SRP_1-Diamond-DSS-I-CD-SG',
            maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-SRP_1-Diamond-DSS-I-CD-MV',
            maskingViewDict['maskingViewName'])

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'ISCSINoFAST'})
    @mock.patch.object(
        volume_types,
        'get_volume_type_qos_specs',
        return_value={'qos_specs': VMAXCommonData.test_volume_type_QOS})
    @mock.patch.object(
        common.VMAXCommon,
        '_register_config_file_from_config_group',
        return_value=None)
    @mock.patch.object(
        utils.VMAXUtils,
        'isArrayV3',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_ecom_connection',
        return_value=FakeEcomConnection())
    def test_initial_setup_qos(self, mock_conn, mock_isArrayV3,
                               mock_register, mock_volumetype_qos,
                               mock_volumetype_extra):
        array_map = [
            {'EcomCACert': None, 'Workload': None, 'EcomServerIp': u'1.1.1.1',
             'PoolName': u'SRP_1', 'EcomPassword': u'pass',
             'SerialNumber': u'1234567891011', 'EcomServerPort': u'10',
             'PortGroup': u'OS-portgroup-PG', 'EcomUserName': u'user',
             'EcomUseSSL': False, 'EcomNoVerification': False,
             'FastPolicy': None, 'SLO': 'Bronze'}]
        with mock.patch.object(
                self.driver.common.utils, 'parse_file_to_get_array_map',
                return_value=array_map):
            with mock.patch.object(
                    self.driver.common.utils, 'extract_record',
                    return_value=array_map[0]):
                extraSpecs = self.driver.common._initial_setup(
                    VMAXCommonData.test_volume_v3)
        self.assertIsNotNone(extraSpecs)
        self.assertEqual(
            VMAXCommonData.test_volume_type_QOS.get('specs'), extraSpecs[
                'qos'])

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict_v3_compression_no_slo(self, mock_find_lun):
        # Compression is no applicable when there is no slo
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'COMPRESSION_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': None,
                      'storagetype:workload': None,
                      'storagetype:disablecompression': 'True'}
        connector = self.data.connector
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertEqual(
            'OS-fakehost-No_SLO-I-SG', maskingViewDict['sgGroupName'])
        self.assertEqual(
            'OS-fakehost-No_SLO-I-MV', maskingViewDict['maskingViewName'])

    @mock.patch.object(
        common.VMAXCommon,
        '_migrate_volume_v3',
        return_value=True)
    def test_slo_workload_migration_compression_enabled(self, mock_migrate):
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'COMPRESSION_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS',
                      'storagetype:disablecompression': 'True'}
        new_type_extra_specs = extraSpecs.copy()
        new_type_extra_specs.pop('storagetype:disablecompression', None)
        new_type = {'extra_specs': new_type_extra_specs}
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeName = 'retype_compression'

        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)

        self.assertTrue(self.driver.common._slo_workload_migration(
            volumeInstance, self.data.test_source_volume_1_v3,
            self.data.test_host_1_v3, volumeName, 'retyping', new_type,
            extraSpecs))

    @mock.patch.object(
        common.VMAXCommon,
        '_migrate_volume_v3',
        return_value=True)
    def test_slo_workload_migration_compression_disabled(self, mock_migrate):
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'COMPRESSION_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS'}
        new_type_extra_specs = extraSpecs.copy()
        new_type_extra_specs['storagetype:disablecompression'] = 'True'
        new_type = {'extra_specs': new_type_extra_specs}
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeName = 'retype_compression'

        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)

        self.assertTrue(self.driver.common._slo_workload_migration(
            volumeInstance, self.data.test_source_volume_1_v3,
            self.data.test_host_1_v3, volumeName, 'retyping', new_type,
            extraSpecs))

    @mock.patch.object(
        common.VMAXCommon,
        '_migrate_volume_v3',
        return_value=True)
    def test_slo_workload_migration_compression_false(self, mock_migrate):
        # Cannot retype because both volume types have the same slo/workload
        # and both are false for disable compression, one by omission
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'COMPRESSION_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS'}
        new_type_extra_specs = extraSpecs.copy()
        new_type_extra_specs['storagetype:disablecompression'] = 'false'
        new_type = {'extra_specs': new_type_extra_specs}
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeName = 'retype_compression'

        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)

        self.assertFalse(self.driver.common._slo_workload_migration(
            volumeInstance, self.data.test_source_volume_1_v3,
            self.data.test_host_1_v3, volumeName, 'retyping', new_type,
            extraSpecs))

    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.extra_specs)
    def test_failover_not_replicated(self, mock_setup):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumes = [self.data.test_volume]
        # Path 1: Failover non replicated volume
        verify_update_fo = [{'volume_id': volumes[0]['id'],
                             'updates': {'status': 'error'}}]
        secondary_id, volume_update = (
            common.failover_host('context', volumes, None))
        self.assertEqual(verify_update_fo, volume_update)
        # Path 2: Failback non replicated volume
        # Path 2a: Volume still available on primary
        common.failover = True
        verify_update_fb1 = [{'volume_id': volumes[0]['id'],
                              'updates': {'status': 'available'}}]
        secondary_id, volume_update_1 = (
            common.failover_host('context', volumes, 'default'))
        self.assertEqual(verify_update_fb1, volume_update_1)
        # Path 2a: Volume not still available on primary
        with mock.patch.object(common, '_find_lun',
                               return_value=None):
            common.failover = True
            secondary_id, volume_update_2 = (
                common.failover_host('context', volumes, 'default'))
            self.assertEqual(verify_update_fo, volume_update_2)

    # create snapshot and immediately delete it fails when snapshot > 50GB
    @mock.patch.object(
        utils.VMAXUtils,
        'get_v3_default_sg_instance_name',
        return_value=(None, None, VMAXCommonData.default_sg_instance_name))
    @mock.patch.object(
        utils.VMAXUtils,
        'is_clone_licensed',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'V3_BE'})
    @mock.patch.object(
        common.VMAXCommon,
        '_get_ecom_connection',
        return_value=FakeEcomConnection())
    def test_create_and_delete_snapshot_100GB(
            self, mock_conn, mock_extraspecs, mock_pool, mock_licence,
            mock_sg):
        common = self.driver.common
        snapshot = self.data.test_snapshot_v3.copy()
        snapshot['volume_size'] = '100'
        with mock.patch.object(common, '_initial_setup',
                               return_value=self.data.extra_specs):
            self.driver.create_snapshot(snapshot)
            self.driver.delete_snapshot(snapshot)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_associated_masking_groups_from_device',
        return_value=[VMAXCommonData.sg_instance_name])
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=[{'CreationClassName': 'Symm_LunMaskingView',
                       'ElementName': 'OS-fakehost-gold-I-MV'}])
    def test_is_volume_multiple_masking_views_false(self, mock_mv_from_sg,
                                                    mock_sg_from_dev):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)
        self.assertFalse(
            common._is_volume_multiple_masking_views(volumeInstance))

    @mock.patch.object(
        masking.VMAXMasking,
        'get_associated_masking_groups_from_device',
        return_value=[VMAXCommonData.sg_instance_name])
    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=[{'CreationClassName': 'Symm_LunMaskingView',
                       'ElementName': 'OS-fakehost-gold-I-MV'},
                      {'CreationClassName': 'Symm_LunMaskingView',
                       'ElementName': 'OS-fakehost-bronze-I-MV'}])
    def test_is_volume_multiple_masking_views_true(self, mock_mv_from_sg,
                                                   mock_sg_from_dev):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)
        self.assertTrue(
            common._is_volume_multiple_masking_views(volumeInstance))

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_storage_group_from_masking_view_instance',
        return_value=VMAXCommonData.sg_instance_name)
    def test_get_storage_group_from_source(self, mock_sg_from_mv):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        mv_instance_name = {'CreationClassName': 'Symm_LunMaskingView',
                            'ElementName': 'OS-fakehost-gold-I-MV'}
        deviceInfoDict = {'controller': mv_instance_name}
        self.assertEqual(VMAXCommonData.sg_instance_name,
                         common._get_storage_group_from_source(
                             deviceInfoDict))

    @mock.patch.object(
        masking.VMAXMasking,
        '_get_storage_group_from_masking_view_instance',
        return_value=VMAXCommonData.sg_instance_name)
    def test_get_storage_group_from_source_except(self, mock_sg_from_mv):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        deviceInfoDict = {}
        self.assertRaises(
            exception.VolumeBackendAPIException,
            common._get_storage_group_from_source, deviceInfoDict)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_port_group_from_masking_view_instance',
        return_value={'CreationClassName': 'CIM_TargetMaskingGroup',
                      'ElementName': 'OS-portgroup-PG'})
    def test_get_port_group_from_source(self, mock_pg_from_mv):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        pg_instance_name = {'CreationClassName': 'CIM_TargetMaskingGroup',
                            'ElementName': 'OS-portgroup-PG'}
        mv_instance_name = {'CreationClassName': 'Symm_LunMaskingView',
                            'ElementName': 'OS-fakehost-gold-I-MV'}
        deviceInfoDict = {'controller': mv_instance_name}
        self.assertEqual(pg_instance_name,
                         common._get_port_group_from_source(
                             deviceInfoDict))

    @mock.patch.object(
        masking.VMAXMasking,
        'get_port_group_from_masking_view_instance',
        return_value={'CreationClassName': 'CIM_TargetMaskingGroup',
                      'ElementName': 'OS-portgroup-PG'})
    def test_get_port_group_from_source_except(self, mock_pg_from_mv):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        deviceInfoDict = {}
        self.assertRaises(
            exception.VolumeBackendAPIException,
            common._get_port_group_from_source, deviceInfoDict)

    def test_manage_existing_get_size(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()

        gb_size = 2
        exp_size = 2
        volume = {}
        metadata = {'key': 'array',
                    'value': '12345'}
        volume['volume_metadata'] = [metadata]
        volume['host'] = 'HostX@Backend#Bronze+SRP_1+1234567891011'
        external_ref = {'source-name': '0123'}
        volumeInstanceName = {'CreationClassName': "Symm_StorageVolume",
                              'DeviceID': "0123",
                              'SystemName': "12345"}

        utils = self.driver.common.utils
        utils.get_volume_size = mock.Mock(
            return_value=int(gb_size * units.Gi))
        utils.find_volume_by_device_id_on_array = mock.Mock(
            return_value=volumeInstanceName)

        size = self.driver.manage_existing_get_size(volume, external_ref)
        self.assertEqual(exp_size, size)

    def test_manage_existing_get_size_fail(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()

        gb_size = 2
        volume = {}
        metadata = {'key': 'array',
                    'value': '12345'}
        volume['volume_metadata'] = [metadata]
        volume['host'] = 'HostX@Backend#Bronze+SRP_1+1234567891011'
        external_ref = {'source-name': '0123'}

        utils = self.driver.common.utils
        utils.get_volume_size = mock.Mock(
            return_value=int(gb_size * units.Gi))

        utils.find_volume_by_device_id_on_array = mock.Mock(
            return_value=None)

        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.common.manage_existing_get_size,
                          volume, external_ref)

    def test_set_volume_replication_if_enabled(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()

        volume = {}
        provider_location = {}

        replication_status = 'replicated'
        replication_driver_data = 'replication_data'

        model_update = {}
        model_update.update(
            {'replication_status': replication_status})
        model_update.update(
            {'replication_driver_data': six.text_type(
                replication_driver_data)})

        extra_specs = self.data.extra_specs_is_re

        common.setup_volume_replication = mock.Mock(
            return_value=(replication_status, replication_driver_data))

        new_model_update = common.set_volume_replication_if_enabled(
            common.conn, extra_specs, volume, provider_location)

        self.assertEqual(new_model_update, model_update)

    @mock.patch.object(
        common.VMAXCommon,
        'set_volume_replication_if_enabled',
        return_value={'replication_status': 'replicated',
                      'replication_driver_data': 'driver_data',
                      'display_name': 'vol1',
                      'provider_location':
                          VMAXCommonData.provider_location3})
    @mock.patch.object(
        utils.VMAXUtils,
        'rename_volume',
        return_value=VMAXCommonData.manage_vol)
    @mock.patch.object(
        utils.VMAXUtils,
        'check_is_volume_in_cinder_managed_pool',
        return_value=True)
    @mock.patch.object(
        utils.VMAXUtils,
        'check_volume_not_replication_source',
        return_value=True)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=('cinder_pool', 'vmax_storage_system'))
    @mock.patch.object(
        utils.VMAXUtils,
        'check_volume_not_in_masking_view',
        return_value=True)
    @mock.patch.object(
        utils.VMAXUtils,
        'find_volume_by_device_id_on_array',
        return_value=VMAXCommonData.test_volume)
    @mock.patch.object(
        utils.VMAXUtils,
        'check_volume_no_fast',
        return_value=True)
    @mock.patch.object(
        utils.VMAXUtils,
        'get_array_and_device_id',
        return_value=('12345', '1'))
    @mock.patch.object(
        common.VMAXCommon,
        '_get_ecom_connection',
        return_value=FakeEcomConnection())
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=VMAXCommonData.extra_specs_is_re)
    def test_manage_existing(self, mock_setup, mock_ecom, mock_ids,
                             mock_vol_fast, mock_vol_by_deviceId,
                             mock_vol_in_mv, mock_pool_sg, mock_vol_rep_src,
                             mock_vol_in_mng_pool, mock_rename_vol,
                             mock_set_vol_rep):
        common = self.driver.common
        volume = EMC_StorageVolume()
        volume.name = 'vol1'
        volume.display_name = 'vol1'
        external_ref = {}

        model_update = {
            'replication_status': 'replicated',
            'replication_driver_data': 'driver_data',
            'display_name': 'vol1',
            'provider_location': six.text_type(
                self.data.provider_location_manage)}

        new_model_update = common.manage_existing(volume,
                                                  external_ref)

        self.assertEqual(model_update, new_model_update)


class VMAXProvisionTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXProvisionTest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'ProvisionTests'
        configuration.config_group = 'ProvisionTests'
        common.VMAXCommon._gather_info = mock.Mock()
        driver = iscsi.VMAXISCSIDriver(
            configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver
        self.driver.utils = utils.VMAXUtils(object)

    @mock.patch.object(
        provision.VMAXProvision,
        'remove_device_from_storage_group')
    def test_remove_device_from_storage_group(self, mock_remove):
        conn = FakeEcomConnection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeName = 'vol1'
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        masking = self.driver.common.masking
        volumeInstance = conn.GetInstance(volumeInstanceName)
        storageGroupName = self.data.storagegroupname
        storageGroupInstanceName = (
            self.driver.common.utils.find_storage_masking_group(
                conn, controllerConfigService, storageGroupName))
        numVolsInSG = 2
        masking._multiple_vols_in_SG(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstance, volumeName, numVolsInSG, extraSpecs)
        masking.provision.remove_device_from_storage_group.assert_called_with(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstanceName, volumeName, extraSpecs)

    def test_add_members_to_masking_group(self):
        conn = FakeEcomConnection()
        controllerConfigService = (
            self.driver.utils.find_controller_configuration_service(
                conn, self.data.storage_system))
        volumeInstanceName = (
            conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeName = 'vol1'
        extraSpecs = {'volume_backend_name': 'V3_BE',
                      'isV3': True,
                      'storagetype:pool': 'SRP_1',
                      'storagetype:workload': 'DSS',
                      'storagetype:slo': 'Bronze'}
        volumeInstance = conn.GetInstance(volumeInstanceName)
        storageGroupName = self.data.storagegroupname
        storageGroupInstanceName = (
            self.driver.common.utils.find_storage_masking_group(
                conn, controllerConfigService, storageGroupName))
        masking = self.driver.common.masking
        masking.provision.add_members_to_masking_group = mock.Mock()
        masking.add_volume_to_storage_group(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstance, volumeName, storageGroupName, extraSpecs)
        masking.provision.add_members_to_masking_group.assert_called_with(
            conn, controllerConfigService, storageGroupInstanceName,
            volumeInstanceName, volumeName, extraSpecs)

    def test_find_consistency_group(self):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        repserv = common.conn.EnumerateInstanceNames(
            "EMC_ReplicationService")[0]
        cgInstanceName, cgName = common._find_consistency_group(
            repserv, VMAXCommonData.test_CG['id'])
        self.assertEqual(VMAXCommonData.replicationgroup_creationclass,
                         cgInstanceName['CreationClassName'])
        self.assertEqual(VMAXCommonData.test_CG['id'], cgName)


class VMAXISCSITest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXISCSITest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'iSCSITests'
        configuration.config_group = 'iSCSITests'
        common.VMAXCommon._gather_info = mock.Mock()
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'hostlunid': 1}, False, {}))
    def test_smis_get_iscsi_properties(self, mock_device):
        iqns_and_ips = (
            [{'iqn': 'iqn.1992-04.com.emc:50000973f006dd80,t,0x0001',
              'ip': '10.10.0.50'},
             {'iqn': 'iqn.1992-04.com.emc:50000973f006dd81,t,0x0001',
              'ip': '10.10.0.51'}])
        properties = self.driver.smis_get_iscsi_properties(
            self.data.test_volume, self.data.connector, iqns_and_ips, True)
        self.assertEqual([1, 1], properties['target_luns'])
        self.assertEqual(['iqn.1992-04.com.emc:50000973f006dd80',
                          'iqn.1992-04.com.emc:50000973f006dd81'],
                         properties['target_iqns'])
        self.assertEqual(['10.10.0.50:3260', '10.10.0.51:3260'],
                         properties['target_portals'])

    @mock.patch.object(
        common.VMAXCommon,
        'find_device_number',
        return_value=({'hostlunid': 1,
                      'storagesystem': VMAXCommonData.storage_system},
                      False, {}))
    @mock.patch.object(
        common.VMAXCommon,
        'initialize_connection',
        return_value=VMAXCommonData.iscsi_device_info)
    def test_initialize_connection_snapshot(self, mock_conn, mock_num):
        data = self.driver.initialize_connection_snapshot(
            self.data.test_snapshot_v3, self.data.connector)
        self.assertEqual('iscsi', data['driver_volume_type'])
        self.assertEqual(1, data['data']['target_lun'])

    @mock.patch.object(
        common.VMAXCommon,
        '_unmap_lun')
    def test_terminate_connection_snapshot(self, mock_unmap):
        common = self.driver.common
        common.conn = FakeEcomConnection()
        self.driver.terminate_connection_snapshot(
            self.data.test_snapshot_v3, self.data.connector)
        common._unmap_lun.assert_called_once_with(
            self.data.test_snapshot_v3, self.data.connector)


class EMCV3ReplicationTest(test.TestCase):

    def setUp(self):
        self.data = VMAXCommonData()

        self.tempdir = tempfile.mkdtemp()
        super(EMCV3ReplicationTest, self).setUp()
        self.config_file_path = None
        self.create_fake_config_file_v3()
        self.addCleanup(self._cleanup)
        self.flags(rpc_backend='oslo_messaging._drivers.impl_fake')

        self.set_configuration()

    def set_configuration(self):
        self.replication_device = [
            {'target_device_id': u'000195900551',
             'remote_port_group': self.data.port_group,
             'remote_pool': 'SRP_1',
             'rdf_group_label': self.data.rdf_group,
             'allow_extend': 'True'}]
        self.configuration = mock.Mock(
            replication_device=self.replication_device,
            cinder_emc_config_file=self.config_file_path,
            config_group='V3')

        def safe_get(key):
            return getattr(self.configuration, key)
        self.configuration.safe_get = safe_get

        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         self.fake_ecom_connection)
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(utils.VMAXUtils, 'isArrayV3',
                         self.fake_is_v3)
        self.mock_object(common.VMAXCommon,
                         '_get_multi_pool_support_enabled_flag',
                         self.fake_get_multi_pool)
        self.mock_object(utils.VMAXUtils,
                         'get_existing_instance',
                         self.fake_get_existing_instance)
        self.mock_object(cinder_utils, 'get_bool_param',
                         return_value=False)
        self.patcher = mock.patch(
            'oslo_service.loopingcall.FixedIntervalLoopingCall',
            new=unit_utils.ZeroIntervalLoopingCall)
        self.patcher.start()

        driver = fc.VMAXFCDriver(configuration=self.configuration)
        driver.db = FakeDB()
        self.driver = driver

    def create_fake_config_file_v3(self):
        doc = minidom.Document()
        emc = doc.createElement("EMC")
        doc.appendChild(emc)

        ecomserverip = doc.createElement("EcomServerIp")
        ecomserveriptext = doc.createTextNode("1.1.1.1")
        emc.appendChild(ecomserverip)
        ecomserverip.appendChild(ecomserveriptext)

        ecomserverport = doc.createElement("EcomServerPort")
        ecomserverporttext = doc.createTextNode("10")
        emc.appendChild(ecomserverport)
        ecomserverport.appendChild(ecomserverporttext)

        ecomusername = doc.createElement("EcomUserName")
        ecomusernametext = doc.createTextNode("user")
        emc.appendChild(ecomusername)
        ecomusername.appendChild(ecomusernametext)

        ecompassword = doc.createElement("EcomPassword")
        ecompasswordtext = doc.createTextNode("pass")
        emc.appendChild(ecompassword)
        ecompassword.appendChild(ecompasswordtext)

        portgroup = doc.createElement("PortGroup")
        portgrouptext = doc.createTextNode(self.data.port_group)
        portgroup.appendChild(portgrouptext)

        pool = doc.createElement("Pool")
        pooltext = doc.createTextNode("SRP_1")
        emc.appendChild(pool)
        pool.appendChild(pooltext)

        array = doc.createElement("Array")
        arraytext = doc.createTextNode("1234567891011")
        emc.appendChild(array)
        array.appendChild(arraytext)

        slo = doc.createElement("ServiceLevel")
        slotext = doc.createTextNode("Bronze")
        emc.appendChild(slo)
        slo.appendChild(slotext)

        workload = doc.createElement("Workload")
        workloadtext = doc.createTextNode("DSS")
        emc.appendChild(workload)
        workload.appendChild(workloadtext)

        portgroups = doc.createElement("PortGroups")
        portgroups.appendChild(portgroup)
        emc.appendChild(portgroups)

        timeout = doc.createElement("Timeout")
        timeouttext = doc.createTextNode("0")
        emc.appendChild(timeout)
        timeout.appendChild(timeouttext)

        filename = 'cinder_emc_config_V3.xml'

        self.config_file_path = self.tempdir + '/' + filename

        f = open(self.config_file_path, 'w')
        doc.writexml(f)
        f.close()

    def fake_ecom_connection(self):
        self.conn = FakeEcomConnection()
        return self.conn

    def fake_is_v3(self, conn, serialNumber):
        return True

    def fake_get_multi_pool(self):
        return False

    def fake_get_existing_instance(self, conn, instancename):
        return instancename

    def _cleanup(self):
        bExists = os.path.exists(self.config_file_path)
        if bExists:
            os.remove(self.config_file_path)
        shutil.rmtree(self.tempdir)

    @mock.patch.object(
        common.VMAXCommon,
        'get_target_instance',
        return_value='volume_instance')
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_setup_volume_replication_success(self, mock_pool,
                                              mock_target):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        sourceVolume = self.data.test_volume_re
        volumeDict = self.data.provider_location
        with mock.patch.object(
                common, 'create_remote_replica',
                return_value=(0, self.data.provider_location2)):
            extraSpecs = self.data.extra_specs_is_re
            rep_status, rep_driver_data = common.setup_volume_replication(
                common.conn, sourceVolume, volumeDict, extraSpecs)
            self.assertEqual(fields.ReplicationStatus.ENABLED, rep_status)
            self.assertEqual(self.data.keybindings2, rep_driver_data)

    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_setup_volume_replication_failed(self, mock_pool):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        sourceVolume = self.data.test_volume_re
        volumeDict = self.data.provider_location
        extraSpecs = self.data.extra_specs_is_re
        self.assertRaises(
            exception.VolumeBackendAPIException,
            common.setup_volume_replication, common.conn, sourceVolume,
            volumeDict, extraSpecs)

    @mock.patch.object(
        common.VMAXCommon,
        '_cleanup_remote_target')
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_cleanup_lun_replication(self, mock_pool, mock_delete):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        volume = self.data.test_volume_re
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        sourceInstance = common.conn.GetInstance(volumeInstanceName)
        extraSpecs = self.data.extra_specs_is_re
        common.cleanup_lun_replication(common.conn, volume, volume['name'],
                                       sourceInstance, extraSpecs)
        with mock.patch.object(
                common.utils, 'find_volume_instance',
                return_value={'ElementName': self.data.test_volume_re['id']}):
            targetInstance = sourceInstance
            repServiceInstanceName = common.conn.EnumerateInstanceNames(
                'EMC_ReplicationService')[0]
            rep_config = common.utils.get_replication_config(
                self.replication_device)
            repExtraSpecs = common._get_replication_extraSpecs(
                extraSpecs, rep_config)
            common._cleanup_remote_target.assert_called_once_with(
                common.conn, repServiceInstanceName, sourceInstance,
                targetInstance, extraSpecs, repExtraSpecs)

    def test_get_rdf_details(self):
        common = self.driver.common
        conn = self.fake_ecom_connection()
        rdfGroupInstance, repServiceInstanceName = (
            common.get_rdf_details(conn, self.data.storage_system))
        self.assertEqual(rdfGroupInstance, self.data.srdf_group_instance)
        self.assertEqual(repServiceInstanceName,
                         conn.EnumerateInstanceNames(
                             'EMC_ReplicationService')[0])

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        '_check_sync_state',
        return_value=6)
    def test_failover_volume_success(self, mock_sync, mock_vol_types):
        volumes = [self.data.test_volume_re]
        rep_data = self.data.replication_driver_data
        loc = six.text_type(self.data.provider_location)
        rep_data = six.text_type(rep_data)
        check_update_list = (
            [{'volume_id': self.data.test_volume_re['id'],
              'updates':
                  {'replication_status': fields.ReplicationStatus.ENABLED,
                   'provider_location': loc,
                   'replication_driver_data': rep_data}}])
        self.driver.common.failover = True
        secondary_id, volume_update_list = (
            self.driver.failover_host('context', volumes, 'default'))
        self.assertEqual(check_update_list, volume_update_list)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    def test_failover_volume_failed(self, mock_vol_types):
        fake_vol = self.data.test_failed_re_volume
        fake_location = six.text_type(
            {'keybindings': 'fake_keybindings'})
        fake_volumes = [fake_vol]
        check_update_list = (
            [{'volume_id': fake_vol['id'],
              'updates':
                  {'replication_status': (
                      fields.ReplicationStatus.FAILOVER_ERROR),
                      'provider_location': fake_location,
                      'replication_driver_data': 'fake_data'}}])
        secondary_id, volume_update_list = (
            self.driver.failover_host('context', fake_volumes, None))
        self.assertEqual(check_update_list, volume_update_list)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        '_check_sync_state',
        return_value=12)
    def test_failback_volume_success(self, mock_sync, mock_vol_types):
        volumes = [self.data.test_volume_re]
        provider_location = self.data.provider_location
        loc = six.text_type(provider_location)
        rep_data = six.text_type(self.data.replication_driver_data)
        check_update_list = (
            [{'volume_id': self.data.test_volume_re['id'],
              'updates':
                  {'replication_status': fields.ReplicationStatus.ENABLED,
                   'replication_driver_data': rep_data,
                   'provider_location': loc}}])
        self.driver.common.failover = True
        secondary_id, volume_update_list = (
            self.driver.failover_host('context', volumes, 'default'))
        six.assertCountEqual(self, check_update_list, volume_update_list)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    def test_failback_volume_failed(self, mock_vol_types):
        fake_vol = self.data.test_failed_re_volume
        fake_location = six.text_type(
            {'keybindings': 'fake_keybindings'})
        fake_volumes = [fake_vol]
        check_update_list = (
            [{'volume_id': fake_vol['id'],
              'updates':
                  {'replication_status': (
                      fields.ReplicationStatus.FAILOVER_ERROR),
                      'provider_location': fake_location,
                      'replication_driver_data': 'fake_data'}}])
        self.driver.common.failover = True
        secondary_id, volume_update_list = (
            self.driver.failover_host('context', fake_volumes, 'default'))
        self.assertEqual(check_update_list, volume_update_list)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    @mock.patch.object(
        utils.VMAXUtils,
        'compare_size',
        return_value=0)
    @mock.patch.object(
        common.VMAXCommon,
        'add_volume_to_replication_group',
        return_value=VMAXCommonData.re_storagegroup)
    @mock.patch.object(
        common.VMAXCommon,
        '_create_remote_replica',
        return_value=(0, VMAXCommonData.provider_location))
    def test_extend_volume_is_replicated_success(
            self, mock_replica, mock_sg, mock_size, mock_vol_types):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        volume = self.data.test_volume_re
        new_size = '2'
        newSizeBits = common.utils.convert_gb_to_bits(new_size)
        extendedVolumeInstance = self.data.volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        extendedVolumeSize = common.utils.get_volume_size(
            self.conn, extendedVolumeInstance)
        self.driver.extend_volume(volume, new_size)
        common.utils.compare_size.assert_called_once_with(
            newSizeBits, extendedVolumeSize)

    @mock.patch.object(
        common.VMAXCommon,
        '_create_remote_replica',
        return_value=(1, 'error'))
    def test_extend_volume_is_replicated_failed(self, mock_replica):
        volume = self.data.test_volume_re
        new_size = '2'
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.extend_volume, volume, new_size)

    @mock.patch.object(
        masking.VMAXMasking,
        'remove_and_reset_members')
    @mock.patch.object(
        common.VMAXCommon,
        'add_volume_to_replication_group',
        return_value=VMAXCommonData.re_storagegroup)
    @mock.patch.object(
        provision_v3.VMAXProvisionV3,
        'get_volume_dict_from_job',
        return_value=VMAXCommonData.provider_location)
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_create_remote_replica_success(self, mock_pool, mock_volume_dict,
                                           mock_sg, mock_return):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        repServiceInstanceName = common.conn.EnumerateInstanceNames(
            'EMC_ReplicationService')[0]
        rdfGroupInstance = self.data.srdf_group_instance
        sourceVolume = self.data.test_volume_re
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        sourceInstance = common.conn.GetInstance(volumeInstanceName)
        targetInstance = sourceInstance
        extraSpecs = self.data.extra_specs_is_re
        rep_config = common.utils.get_replication_config(
            self.replication_device)
        referenceDict = VMAXCommonData.provider_location
        rc, rdfDict = common.create_remote_replica(
            common.conn, repServiceInstanceName, rdfGroupInstance,
            sourceVolume, sourceInstance, targetInstance,
            extraSpecs, rep_config)
        self.assertEqual(referenceDict, rdfDict)

    @mock.patch.object(
        masking.VMAXMasking,
        'remove_and_reset_members')
    @mock.patch.object(
        common.VMAXCommon,
        '_cleanup_remote_target')
    @mock.patch.object(
        common.VMAXCommon,
        '_get_pool_and_storage_system',
        return_value=(None, VMAXCommonData.storage_system))
    def test_create_remote_replica_failed(self, mock_pool,
                                          mock_cleanup, mock_return):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        repServiceInstanceName = common.conn.EnumerateInstanceNames(
            'EMC_ReplicationService')[0]
        rdfGroupInstance = self.data.srdf_group_instance
        sourceVolume = self.data.test_volume_re
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        sourceInstance = common.conn.GetInstance(volumeInstanceName)
        targetInstance = sourceInstance
        extraSpecs = self.data.extra_specs_is_re
        rep_config = common.utils.get_replication_config(
            self.replication_device)
        repExtraSpecs = common._get_replication_extraSpecs(
            extraSpecs, rep_config)
        with mock.patch.object(common.provisionv3,
                               '_create_element_replica_extra_params',
                               return_value=(9, 'error')):
            with mock.patch.object(common.utils,
                                   'wait_for_job_complete',
                                   return_value=(9, 'error')):
                self.assertRaises(
                    exception.VolumeBackendAPIException,
                    common.create_remote_replica, common.conn,
                    repServiceInstanceName, rdfGroupInstance, sourceVolume,
                    sourceInstance, targetInstance, extraSpecs, rep_config)
                common._cleanup_remote_target.assert_called_once_with(
                    common.conn, repServiceInstanceName, sourceInstance,
                    targetInstance, extraSpecs, repExtraSpecs)

    @mock.patch.object(
        masking.VMAXMasking,
        'get_masking_view_from_storage_group',
        return_value=None)
    def test_add_volume_to_replication_group_success(self, mock_mv):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        controllerConfigService = (
            common.utils.find_controller_configuration_service(
                common.conn, self.data.storage_system))
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)
        volumeName = self.data.test_volume_re['name']
        extraSpecs = self.data.extra_specs_is_re
        with mock.patch.object(
                common.utils, 'find_storage_masking_group',
                return_value=self.data.default_sg_instance_name):
            common.add_volume_to_replication_group(
                common.conn, controllerConfigService,
                volumeInstance, volumeName, extraSpecs)

    def test_add_volume_to_replication_group_failed(self):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        controllerConfigService = (
            common.utils.find_controller_configuration_service(
                common.conn, self.data.storage_system))
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)
        volumeName = self.data.test_volume_re['name']
        extraSpecs = self.data.extra_specs_is_re
        with mock.patch.object(
                common.utils, 'find_storage_masking_group',
                return_value=None):
            self.assertRaises(exception.VolumeBackendAPIException,
                              common.add_volume_to_replication_group,
                              common.conn, controllerConfigService,
                              volumeInstance, volumeName, extraSpecs)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    @mock.patch.object(
        common.VMAXCommon,
        'add_volume_to_replication_group')
    @mock.patch.object(
        common.VMAXCommon,
        '_create_v3_volume',
        return_value=(0, VMAXCommonData.provider_location,
                      VMAXCommonData.storage_system))
    def test_create_replicated_volume_success(self, mock_create, mock_add,
                                              mock_vol_types):
        model_update = self.driver.create_volume(
            self.data.test_volume_re)
        rep_status = model_update['replication_status']
        rep_data = model_update['replication_driver_data']
        self.assertEqual(fields.ReplicationStatus.ENABLED,
                         rep_status)
        self.assertTrue(isinstance(rep_data, six.text_type))
        self.assertIsNotNone(rep_data)

    @mock.patch.object(
        common.VMAXCommon,
        'setup_volume_replication',
        return_value=(fields.ReplicationStatus.ENABLED,
                      {'provider_location':
                          VMAXCommonData.provider_location}))
    @mock.patch.object(
        common.VMAXCommon,
        '_initial_setup',
        return_value=(VMAXCommonData.extra_specs_is_re))
    @mock.patch.object(
        common.VMAXCommon,
        '_sync_check')
    @mock.patch.object(
        common.VMAXCommon,
        'add_volume_to_replication_group')
    @mock.patch.object(
        common.VMAXCommon,
        '_create_cloned_volume',
        return_value=VMAXCommonData.provider_location)
    def test_create_replicated_volume_from_snap_success(
            self, mock_create, mock_add, mock_sync_check, mock_setup,
            mock_vol_rep):
        model_update = self.driver.create_volume_from_snapshot(
            self.data.test_volume_re, self.data.test_snapshot_re)
        rep_status = model_update['replication_status']
        rep_data = model_update['replication_driver_data']
        self.assertEqual(fields.ReplicationStatus.ENABLED,
                         rep_status)
        self.assertTrue(isinstance(rep_data, six.text_type))
        self.assertTrue(rep_data)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    @mock.patch.object(
        common.VMAXCommon,
        '_cleanup_replication_source')
    @mock.patch.object(
        common.VMAXCommon,
        '_create_v3_volume',
        return_value=(0, VMAXCommonData.provider_location,
                      VMAXCommonData.storage_system))
    def test_create_replicated_volume_failed(self, mock_create, mock_cleanup,
                                             mock_vol_types):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        volumeName = self.data.test_volume_re['id']
        volumeDict = self.data.provider_location
        extraSpecs = self.data.extra_specs_is_re
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.create_volume, self.data.test_volume_re)
        common._cleanup_replication_source.assert_called_once_with(
            common.conn, volumeName, volumeDict, extraSpecs)

    @mock.patch.object(
        common.VMAXCommon,
        '_delete_from_pool_v3')
    def test_cleanup_replication_source(self, mock_delete):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        volumeName = self.data.test_volume_re['name']
        volumeDict = self.data.provider_location
        extraSpecs = self.data.extra_specs_is_re
        storageConfigService = (
            common.utils.find_storage_configuration_service(
                common.conn, self.data.storage_system))
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        sourceInstance = common.conn.GetInstance(volumeInstanceName)
        deviceId = self.data.test_volume_re['device_id']
        common._cleanup_replication_source(
            common.conn, volumeName, volumeDict, extraSpecs)
        common._delete_from_pool_v3.assert_called_once_with(
            storageConfigService, sourceInstance,
            volumeName, deviceId, extraSpecs)

    @mock.patch.object(
        common.VMAXCommon,
        '_delete_from_pool_v3')
    def test_cleanup_remote_target(self, mock_delete):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        repServiceInstanceName = common.conn.EnumerateInstanceNames(
            'EMC_ReplicationService')[0]
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        sourceInstance = common.conn.GetInstance(volumeInstanceName)
        targetInstance = sourceInstance.copy()
        targetStorageConfigService = (
            common.utils.find_storage_configuration_service(
                common.conn, self.data.storage_system))
        deviceId = targetInstance['DeviceID']
        volumeName = targetInstance['Name']
        extraSpecs = self.data.extra_specs_is_re
        rep_config = common.utils.get_replication_config(
            self.replication_device)
        repExtraSpecs = common._get_replication_extraSpecs(
            extraSpecs, rep_config)
        common._cleanup_remote_target(
            common.conn, repServiceInstanceName, sourceInstance,
            targetInstance, extraSpecs, repExtraSpecs)
        common._delete_from_pool_v3.assert_called_once_with(
            targetStorageConfigService, targetInstance, volumeName,
            deviceId, repExtraSpecs)

    @mock.patch.object(
        volume_types,
        'get_volume_type_extra_specs',
        return_value={'volume_backend_name': 'VMAXReplication',
                      'replication_enabled': '<is> True'})
    @mock.patch.object(
        common.VMAXCommon,
        'cleanup_lun_replication')
    def test_delete_re_volume(self, mock_cleanup, mock_vol_types):
        common = self.driver.common
        common.conn = self.fake_ecom_connection()
        volume = self.data.test_volume_re
        volumeName = volume['name']
        volumeInstanceName = (
            common.conn.EnumerateInstanceNames("EMC_StorageVolume")[0])
        volumeInstance = common.conn.GetInstance(volumeInstanceName)
        extraSpecs = self.data.extra_specs_is_re
        self.driver.delete_volume(volume)
        common.cleanup_lun_replication.assert_called_once_with(
            common.conn, volume, volumeName, volumeInstance, extraSpecs)

    def test_failback_failover_wrong_state(self):
        common = self.driver.common
        volumes = [self.data.test_volume_re]
        # failover command, backend already failed over
        common.failover = True
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.failover_host,
                          'context', volumes, None)
        # failback command, backend not failed over
        common.failover = False
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.failover_host,
                          'context', volumes, 'default')


class VMAXInitiatorCheckFalseTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXInitiatorCheckFalseTest, self).setUp()

        configuration = mock.Mock()
        configuration.safe_get.return_value = 'initiatorCheckTest'
        configuration.config_group = 'initiatorCheckTest'

        common.VMAXCommon._gather_info = mock.Mock()
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         FakeEcomConnection())
        self.mock_object(utils.VMAXUtils,
                         'find_controller_configuration_service',
                         return_value=None)
        driver = iscsi.VMAXISCSIDriver(configuration=configuration)
        driver.db = FakeDB()
        self.driver = driver

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict(self, mock_find_lun):
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'INITIATOR_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS'}
        connector = self.data.connector
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertFalse(maskingViewDict['initiatorCheck'])


class VMAXInitiatorCheckTrueTest(test.TestCase):
    def setUp(self):
        self.data = VMAXCommonData()

        super(VMAXInitiatorCheckTrueTest, self).setUp()

        self.configuration = mock.Mock(
            replication_device={},
            initiator_check='True',
            config_group='initiatorCheckTest')

        def safe_get(key):
            return getattr(self.configuration, key)
        self.configuration.safe_get = safe_get
        common.VMAXCommon._gather_info = mock.Mock()
        instancename = FakeCIMInstanceName()
        self.mock_object(utils.VMAXUtils, 'get_instance_name',
                         instancename.fake_getinstancename)
        self.mock_object(common.VMAXCommon, '_get_ecom_connection',
                         FakeEcomConnection())
        self.mock_object(utils.VMAXUtils,
                         'find_controller_configuration_service',
                         return_value=None)
        driver = iscsi.VMAXISCSIDriver(configuration=self.configuration)
        driver.db = FakeDB()
        self.driver = driver

    @mock.patch.object(
        common.VMAXCommon,
        '_find_lun',
        return_value=(
            {'SystemName': VMAXCommonData.storage_system}))
    def test_populate_masking_dict(self, mock_find_lun):
        extraSpecs = {'storagetype:pool': u'SRP_1',
                      'volume_backend_name': 'INITIATOR_BE',
                      'storagetype:array': u'1234567891011',
                      'isV3': True,
                      'portgroupname': u'OS-portgroup-PG',
                      'storagetype:slo': u'Diamond',
                      'storagetype:workload': u'DSS'}
        connector = self.data.connector
        maskingViewDict = self.driver.common._populate_masking_dict(
            self.data.test_volume, connector, extraSpecs)
        self.assertTrue(maskingViewDict['initiatorCheck'])
