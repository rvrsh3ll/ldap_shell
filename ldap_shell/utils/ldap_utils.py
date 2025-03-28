from typing import Optional
import re
from struct import pack, unpack
import logging
from ldap_shell.utils.ldaptypes import SR_SECURITY_DESCRIPTOR, LDAP_SID, ACL
from ldap3.protocol.microsoft import security_descriptor_control

class LdapUtils:
    @staticmethod
    def get_dn(client, domain_dumper, name: str) -> Optional[str]:
        """Get DN with automatic computer account retry"""
        result = LdapUtils._search_with_retry(
            client, 
            domain_dumper, 
            name,
            attributes=['distinguishedName']
        )
        return result.entry_dn if result else None

    @staticmethod
    def get_attribute(client, domain_dumper, name: str, attribute: str) -> Optional[str]:
        """Get attribute with computer account auto-retry"""
        result = LdapUtils._search_with_retry(
            client, 
            domain_dumper, 
            name,
            attributes=[attribute]
        )
        return result[attribute].value if result else None

    @staticmethod
    def get_sid(client, domain_dumper, name: str) -> Optional[str]:
        """Get SID with computer account auto-retry"""
        result = LdapUtils._search_with_retry(
            client, 
            domain_dumper, 
            name,
            attributes=['objectSid']
        )
        return result['objectSid'].value if result else None

    @staticmethod
    def sid_to_user(client, domain_dumper, sid: str) -> str:
        """Convert SID to samAccountName"""
        client.search(
            domain_dumper.root,
            f'(objectSid={sid})',
            attributes=['sAMAccountName']
        )
        if client.entries:
            return client.entries[0]['sAMAccountName'].value
        return None

    @staticmethod
    def check_dn(client, domain_dumper, dn: str) -> bool:
        """Check if DN is valid"""
        client.search(
            domain_dumper.root,
            f'(distinguishedName={dn})',
            attributes=['objectClass']
        )
        return len(client.entries) > 0

    @staticmethod
    def get_domain_name(dn: str) -> str:
        """Get domain name from DN"""
        return re.sub(',DC=', '.', dn[dn.find('DC='):], flags=re.I)[3:]

    @staticmethod
    def get_info_by_dn(client, domain_dumper, dn: str) -> Optional[tuple[bytes, str]]:
        """Get info by DN"""
        client.search(
            domain_dumper.root,
            f'(distinguishedName={dn})',
            attributes=['nTSecurityDescriptor', 'objectSid'],
            controls=security_descriptor_control(sdflags=0x04)
        )
        if len(client.entries) > 0:
            return client.entries[0]['nTSecurityDescriptor'].raw_values, client.entries[0]['objectSid'].value
        return None

    @staticmethod
    def get_name_from_dn(dn: str) -> Optional[str]:
        """Get name from DN"""
        return dn.split(',')[0].split('=')[1]
    
    @staticmethod
    def _search_with_retry(client, domain_dumper, name: str, attributes: list):
        # Initial search
        client.search(
            domain_dumper.root,
            f'(sAMAccountName={name})',
            attributes=attributes
        )
        if client.entries:
            return client.entries[0]
        
        # If not found, try adding $ for computer accounts
        if not name.endswith('$'):
            retry_name = f'{name}$'
            client.search(
                domain_dumper.root,
                f'(sAMAccountName={retry_name})',
                attributes=attributes
            )
            if client.entries:
                logging.debug(f'Auto-corrected computer account name: {name} -> {retry_name}')
                return client.entries[0]
        
        return None

    @staticmethod
    def bin_to_string(uuid):
        uuid1, uuid2, uuid3 = unpack('<LHH', uuid[:8])
        uuid4, uuid5, uuid6 = unpack('>HHL', uuid[8:16])
        return '%08X-%04X-%04X-%04X-%04X%08X' % (uuid1, uuid2, uuid3, uuid4, uuid5, uuid6)

    @staticmethod
    def string_to_bin(uuid):
        # If a UUID in the 00000000-0000-0000-0000-000000000000 format, parse it as Variant 2 UUID
        # The first three components of the UUID are little-endian, and the last two are big-endian
        matches = re.match(
            r"([\dA-Fa-f]{8})-([\dA-Fa-f]{4})-([\dA-Fa-f]{4})-([\dA-Fa-f]{4})-([\dA-Fa-f]{4})([\dA-Fa-f]{8})",
            uuid)
        (uuid1, uuid2, uuid3, uuid4, uuid5, uuid6) = [int(x, 16) for x in matches.groups()]
        uuid = pack('<LHH', uuid1, uuid2, uuid3)
        uuid += pack('>HHL', uuid4, uuid5, uuid6)
        return uuid
    
    @staticmethod
    def create_empty_sd():
        sd = SR_SECURITY_DESCRIPTOR()
        sd['Revision'] = b'\x01'
        sd['Sbz1'] = b'\x00'
        sd['Control'] = 32772
        sd['OwnerSid'] = LDAP_SID()
        # BUILTIN\Administrators
        sd['OwnerSid'].fromCanonical('S-1-5-32-544')
        sd['GroupSid'] = b''
        sd['Sacl'] = b''
        acl = ACL()
        acl['AclRevision'] = 4
        acl['Sbz1'] = 0
        acl['Sbz2'] = 0
        acl.aces = []
        sd['Dacl'] = acl
        return sd