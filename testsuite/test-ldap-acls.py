"""Tests for access control and other rules in LDAP

Most of these focus on ACLs, but some rules are implemented in other ways.
All get tested here as they all contribute to the overall security policy.

The actual tests all have names like test_T1234_mozillian_do_something
where the T1234 bit is a cross-reference to the LDAP design document.
There may be several tests with the same cross-ref.

Andrew Findlay
21 June 2011
"""

import sys
import unittest
import re
import ldap
import ldap.modlist
from ldif import LDIFParser

########################################################################
# Configuration
########################################################################

ldap_url = 'ldap://localhost:1389/'
ldap_suffix = 'dc=mozillians,dc=org'

people_node = 'ou=People,' + ldap_suffix

# Credentials for the all-powerful user
# (Don't put the password for your production server here!)
ldap_rootDN = 'cn=root,dc=mozillians,dc=org'
ldap_rootPW = 'secret'

# Credentials for an existing non-vouched Applicant
ldap_applicant001DN = 'uniqueIdentifier=test001,ou=people,dc=mozillians,dc=org'
ldap_applicant001PW = 'secret'

# Credentials for an existing vouched Mozillian
ldap_mozillian011DN = 'uniqueIdentifier=test011,ou=people,dc=mozillians,dc=org'
ldap_mozillian011PW = 'secret'

# Credentials for a system account
ldap_sys999DN = 'uid=test999,ou=accounts,ou=system,dc=mozillians,dc=org'
ldap_sys999PW = 'secret'

# DNs of some victims
ldap_applicant002DN = 'uniqueIdentifier=test002,ou=people,dc=mozillians,dc=org'
ldap_mozillian012DN = 'uniqueIdentifier=test012,ou=people,dc=mozillians,dc=org'

# Where the LDAP server keeps its monitoring stats
monitor_suffix = 'cn=Monitor'
# ...and the group you have to be in if you want to see that data
monitor_group = 'cn=monitors,ou=groups,ou=system,dc=mozillians,dc=org'

# Group of accounts that may replicate the entire DIT
replicator_group = 'cn=replicators,ou=groups,ou=system,dc=mozillians,dc=org'

# The name of the setup file
setup_ldif = 'setup.ldif'

########################################################################
# Globals
########################################################################

# Keep a list of entries that need deleting in tearDown
global entry_list
entry_list = []

########################################################################
# Utility functions
########################################################################

# Get list of attributes in result
#
def getAttrNames ( ldap_result ):
    # ldap_result has the form:
    # (dn, dict)
    # where dict has a list of values for each named attribute

    return ldap_result[1].keys()

# Get list of values for attribute
# If there is no such attribute then we return an empty list
#
def getAttrValueList( ldap_result, attrname ):
    # ldap_result has the form:
    # (dn, dict)
    # where dict has a list of values for each named attribute

    # First problem: dictionary keys are case-sensitive.
    #                Attribute names are not.
    myattr = None
    for k in ldap_result[1].keys():
    	if k.lower() == attrname.lower():
	    myattr = k
    return ldap_result[1].get(myattr,[])

# Get the first value of an attribute
# If there is no such attribute then we return None
#
def getAttrValue( ldap_result, attrname ):
    # ldap_result has the form:
    # (dn, dict)
    # where dict has a list of values for each named attribute
    attr_list = getAttrValueList( ldap_result, attrname )
    if not attr_list:
	return None
    else:
	return attr_list[0]

# Check for a value of an attribute that matches a given pattern
#
def attrValueMatch( ldap_result, attrname, pattern ):
    attr_list = getAttrValueList( ldap_result, attrname )
    if not attr_list:
	return None
    else:
        for val in attr_list:
	    # print "TESTING:", val
	    if re.search(pattern,val):
		return True
    return False

# Load an LDIF file
# Used for setting up test cases
#
class LdifLoader(LDIFParser):
    def handle(self,dn,entry):
        # print dn
	# Try to delete the entry before adding it, just in case...
	try:
	    self.ldap_handle.delete_s(dn)
	except ldap.NO_SUCH_OBJECT:
	    pass
	# We need to delete this later
	entry_list.append(dn)
	# Add the entry
	self.ldap_handle.add_s(dn,ldap.modlist.addModlist(entry))


########################################################################
# Common test-fixture code
########################################################################

def setUpCommon(self):
    # Set up the connections, and by doing so implement test_T0005_anon_bind
    try:
	self.ldap_anon = ldap.initialize(ldap_url)

	self.ldap_rootDN = ldap.initialize(ldap_url)
	self.ldap_rootDN.simple_bind_s(ldap_rootDN,ldap_rootPW)

	ldifparser = LdifLoader(open(setup_ldif, 'r'), None)
	ldifparser.ldap_handle = self.ldap_rootDN
	ldifparser.parse()

	self.ldap_applicant001 = ldap.initialize(ldap_url)
	self.ldap_applicant001.simple_bind_s(ldap_applicant001DN,ldap_applicant001PW)

	self.ldap_mozillian011 = ldap.initialize(ldap_url)
	self.ldap_mozillian011.simple_bind_s(ldap_mozillian011DN,ldap_mozillian011PW)

	self.ldap_sys999 = ldap.initialize(ldap_url)
	self.ldap_sys999.simple_bind_s(ldap_sys999DN,ldap_sys999PW)

    except ldap.LDAPError:
		self.fail( "LDAP connection setup error " + str(sys.exc_info()[0]) )


def tearDownCommon(self):
    global entry_list

    # We delete the longest DNs first to avoid trying to delete
    # non-leaf objects
    for dn in sorted(entry_list, key=len, reverse=True):
	# print dn
	# It is OK to ignore an error if we are deleting something that
	# has gone already
	try:
	    self.ldap_rootDN.delete_s(dn)
	except ldap.NO_SUCH_OBJECT:
	    pass
	
    # We have deleted everything that was on the list
    entry_list = []

    self.ldap_anon.unbind()
    self.ldap_rootDN.unbind()
    self.ldap_applicant001.unbind()
    self.ldap_mozillian011.unbind()
    self.ldap_sys999.unbind()

########################################################################
# Tests
########################################################################

class LdapUserTests(unittest.TestCase):

    def setUp(self):
    	setUpCommon(self)

    def tearDown(self):
    	tearDownCommon(self)

    # All users including Anon should be able to read the schema
    def read_root_DSE_and_schema(self, user, ldap_conn):
	# Read subschemaSubentry from the null DN
	try:
	    res = ldap_conn.search_s(
		    '',
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['subschemaSubentry'] )

	    # We only expect one value here
	    schema_ptr = getAttrValue(res[0],'subschemaSubentry')
	    if schema_ptr:
		self.assertRegexpMatches(
			schema_ptr, '^[a-zA-Z]+=',
			'root DSE should contain a valid schema pointer')
            else:
	        self.fail( user + " did not get a subschemaSubentry attribute from the root DSE" )

        except ldap.LDAPError:
	    self.fail( user + " cannot read root DSE " + str(sys.exc_info()[0]) )

	# Now check that we can read the schema
	try:
	    res = ldap_conn.search_s(
		    schema_ptr,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['attributetypes','objectclasses'])
        except ldap.LDAPError:
	    self.fail( user + " cannot read schema subentry " + schema_ptr + " " + str(sys.exc_info()[0]) )

        # Did we get any Mozillians attributes?
	self.assertTrue( attrValueMatch( res[0], 'attributetypes', 'mozillians' ),
	                 "Mozillians attribute types must be listed in schema" )


    # Changing password
    def change_and_check_password(self, user, userDN, ldap_conn, old_pw, new_pw):
        try:
	    ldap_conn.passwd_s(userDN, old_pw, new_pw)
        except:
	    self.fail( user + " cannot change password: " + str(sys.exc_info()[0]) )

        try:
            ldap_check = ldap.initialize(ldap_url)
	    ldap_check.simple_bind_s(userDN, new_pw)
        except:
	    self.fail( user + " cannot bind with new password: " + str(sys.exc_info()[0]) )

        ldap_check.unbind()


    # Changing own user attributes
    def change_user_attributes(self, user, userDN, ldap_conn):
        try:
	    ldap_conn.modify_s(
	        userDN,
		    [
		        (ldap.MOD_REPLACE,'cn','modified CN'),
		        (ldap.MOD_REPLACE,'sn','modified SN'),
		        (ldap.MOD_REPLACE,'displayName','modified displayName'),
		        (ldap.MOD_REPLACE,'mail',['new@mail.one','new@mail.two']),
		        (ldap.MOD_REPLACE,'uid','modified UID'),
		        (ldap.MOD_REPLACE,'telephoneNumber',['+1 234','+5-678-90']),
		        (ldap.MOD_REPLACE,'description','modified description'),
		        (ldap.MOD_REPLACE,'jpegPhoto','modified jpegPhoto'),
		    ]
		)
        except ldap.LDAPError:
	    self.fail( user + " cannot modify their own user atttributes " + str(sys.exc_info()[0]) )



    #######################################################################################
    # Actual tests start here
    #######################################################################################

    def test_T0015_anon_read_suffix(self):
        res = self.ldap_anon.search_s(ldap_suffix,ldap.SCOPE_BASE,'(objectclass=*)')
	self.assertTrue( attrValueMatch( res[0], 'dc', 'mozillians' ),
	         'suffix entry should have an attribute dc=mozillians')

    def test_T0016_anon_read_people_container(self):
        res = self.ldap_anon.search_s(people_node,ldap.SCOPE_BASE,'(objectclass=*)')
	self.assertTrue( attrValueMatch( res[0], 'ou', 'people' ),
	         'ou=people entry should have an attribute ou=people')

    def test_T0010_anon_read_root_DSE_and_schema(self):
	self.read_root_DSE_and_schema("Anon", self.ldap_anon)

    def test_T0010_applicant_read_root_DSE_and_schema(self):
	self.read_root_DSE_and_schema("Applicant 001", self.ldap_applicant001)

    def test_T0010_mozillian_read_root_DSE_and_schema(self):
	self.read_root_DSE_and_schema("Mozillian 011", self.ldap_mozillian011)

    def test_T0020_anon_search_person(self):
	# Anon trying to find a person entry
	# This should work, but not expose any data apart from the DN
	try:
	    res = self.ldap_anon.search_s(
		    people_node,
		    ldap.SCOPE_SUBTREE,
		    filterstr='(uid=test002)' )

	    self.assertEqual( len(res), 1,
	            "Anon search for (uid=test002) should return exactly one entry. We got "+str(len(res)) )
            # print res[0]
        except ldap.LDAPError:
	    self.fail( "Anon cannot search under "+people_node+" " + str(sys.exc_info()[0]) )

        # Now test to see if we got any attributes that we should not see
	for attr in getAttrNames(res[0]):
	    if attr.lower() != 'uniqueIdentifier'.lower():
	        self.fail( "Anon should not be able to read attributes from user entries. Got: " +
		           str(getAttrNames(res[0])) )

    def test_T0030_anon_search_multi(self):
	# Anon trying to find multiple entries
	# This should limit at 2 entries returned but the search filter matches 3
	# so we expect to get an exception.
	# LDAP actually supplies the entries, but Python LDAP does not deliver them to us.
	try:
	    with self.assertRaises(ldap.SIZELIMIT_EXCEEDED):
		res = self.ldap_anon.search_s(
			people_node,
			ldap.SCOPE_SUBTREE,
			filterstr='(uid=test00*)' )

        except ldap.LDAPError:
	    self.fail( "Anon cannot search under "+people_node+" " + str(sys.exc_info()[0]) )

    def test_T6040_applicant_search_person(self):
	# Applicant trying to find a person entry that is not their own
	# This should work, but not expose any data apart from the DN
	try:
	    res = self.ldap_applicant001.search_s(
		    people_node,
		    ldap.SCOPE_SUBTREE,
		    filterstr='(uid=test002)' )

	    self.assertEqual( len(res), 1,
	            "Applicant search for (uid=test002) should return exactly one entry. We got "+str(len(res)) )
        except ldap.LDAPError:
	    self.fail( "Applicant cannot search under "+people_node+" " + str(sys.exc_info()[0]) )

        # Now test to see if we got any attributes that we should not see
	for attr in getAttrNames(res[0]):
	    if attr.lower() != 'uniqueIdentifier'.lower():
	        self.fail( "Applicant should not be able to read attributes from user entries. Got: " +
		           str(getAttrNames(res[0])) )

# It is not practical to enforce different limits on Applicants and Mozillians
# with the current implementation because the limits statement in OpenLDAP does not accept
# set specifications
#
#    def test_T6050_applicant_search_multi(self):
#	# Applicant trying to find multiple entries
#	# The filter matches 3 in this case
#	# This should limit at 2 entries returned
#	try:
#	    with self.assertRaises(ldap.SIZELIMIT_EXCEEDED):
#		res = self.ldap_applicant001.search_s(
#			people_node,
#			ldap.SCOPE_SUBTREE,
#			filterstr='(uid=test00*)' )
#
#        except ldap.LDAPError:
#	    self.fail( "Applicant cannot search under "+people_node+" " + str(sys.exc_info()[0]) )

    def test_T6030_mozillian_search_person(self):
	# Mozillian trying to find a person entry
	# This should work, but not expose any data apart from the DN
	try:
	    res = self.ldap_mozillian011.search_s(
		    people_node,
		    ldap.SCOPE_SUBTREE,
		    filterstr='(uid=test002)' )

	    self.assertEqual( len(res), 1,
	            "Mozillian search for (uid=test002) should return exactly one entry. We got "+str(len(res)) )
            # print res[0]
        except ldap.LDAPError:
	    self.fail( "Mozillian cannot search under "+people_node+" " + str(sys.exc_info()[0]) )

	# Check that we got values for the basic attributes
	if not getAttrValue(res[0],'objectClass'):
	    self.fail( "Mozillian should see the objectClass value" )
	if not getAttrValue(res[0],'cn'):
	    self.fail( "Mozillian should see the cn value" )
	if not getAttrValue(res[0],'sn'):
	    self.fail( "Mozillian should see the sn value" )
	if not getAttrValue(res[0],'uid'):
	    self.fail( "Mozillian should see the uid value" )
	if not getAttrValue(res[0],'uniqueIdentifier'):
	    self.fail( "Mozillian should see the uniqueIdentifier value" )

        # Now test to see if we got any attributes that we should not see
	if getAttrValue(res[0],'userPassword'):
	    self.fail( "Mozillian should not be able to read passwords" )

    def test_T0030_mozillian_search_multi(self):
	# Mozillian trying to find multiple entries
	# This should limit at rather more than 2 entries returned
	try:
	    res = self.ldap_mozillian011.search_s(
		    people_node,
		    ldap.SCOPE_SUBTREE,
		    filterstr='(uid=test*)' )

	    self.assertGreater( len(res), 2,
	            "Mozillian search for (uid=test*) should return more than 2 entries. We got "+str(len(res)) )
            # print res[0]
        except ldap.LDAPError:
	    self.fail( "Mozillian cannot search under "+people_node+" " + str(sys.exc_info()[0]) )


    def test_T1010_applicant_change_password(self):
        self.change_and_check_password(
	        'Applicant',
                ldap_applicant001DN,
		self.ldap_applicant001,
		None,
		'evenmoresecret' )

    def test_T1010_mozillian_change_password(self):
        self.change_and_check_password(
	        'Mozillian',
                ldap_mozillian011DN,
		self.ldap_mozillian011,
		None,
		'evenmoresecret' )

    def test_T1020_change_others_password(self):
	# Try to change other people's passwords
	with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_mozillian011.passwd_s(ldap_applicant002DN, None, 'owned!')

	with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_mozillian011.passwd_s(ldap_mozillian012DN, None, 'owned!')

	with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_applicant001.passwd_s(ldap_applicant002DN, None, 'owned!')

	with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_applicant001.passwd_s(ldap_mozillian012DN, None, 'owned!')

    def test_T6010_applicant_change_user_attributes(self):
        self.change_user_attributes(
	        'Applicant',
                ldap_applicant001DN,
		self.ldap_applicant001 )

    def test_T6010_mozillian_change_user_attributes(self):
        self.change_user_attributes(
	        'Mozillian',
                ldap_mozillian011DN,
		self.ldap_mozillian011 )

    def test_T6010_mozillian_delete_uid(self):
	# Users should not be able to delete uid as then it will be
	# impossible for them to log in again
	# The error here is OBJECT_CLASS_VIOLATION because this is enforced
	# by a DIT content rule rather than an ACL
        with self.assertRaises(ldap.OBJECT_CLASS_VIOLATION):
	    self.ldap_mozillian011.modify_s(
		    ldap_mozillian011DN,
		    [
		        (ldap.MOD_DELETE,'uid',None),
		    ]
		)


    def test_T6020_mozillian_read_obscure_attrs(self):
	# Mozillian reading more obscure attributes in their own entry
	try:
	    res = self.ldap_mozillian011.search_s(
		    ldap_mozillian011DN,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['mozilliansVouchedBy','modifiersName','modifyTimestamp','userPassword'] )
        except ldap.LDAPError:
	    self.fail( "Mozillian cannot search own entry " + str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'modifiersName'):
	    self.fail( "Mozillian should see their own modifiersName value" )
	if not getAttrValue(res[0],'modifyTimestamp'):
	    self.fail( "Mozillian should see their own modifyTimestamp value" )
	if not getAttrValue(res[0],'mozilliansVouchedBy'):
	    self.fail( "Mozillian should see their own mozilliansVouchedBy value" )
	# Should NOT see own password
	if getAttrValue(res[0],'userPassword'):
	    self.fail( "Mozillian should not see their own userPassword value" )

    def test_T6020_applicant_read_own_attrs(self):
	# Applicant reading common attributes in their own entry
	try:
	    res = self.ldap_applicant001.search_s(
		    ldap_applicant001DN,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)' )
        except ldap.LDAPError:
	    self.fail( "Applicant cannot search own entry " + str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'objectClass'):
	    self.fail( "Applicant should see their own objectClass value" )
	if not getAttrValue(res[0],'cn'):
	    self.fail( "Applicant should see their own cn value" )
	if not getAttrValue(res[0],'sn'):
	    self.fail( "Applicant should see their own sn value" )
	if not getAttrValue(res[0],'description'):
	    self.fail( "Applicant should see their own description value" )
	if not getAttrValue(res[0],'mail'):
	    self.fail( "Applicant should see their own mail value" )

    def test_T6020_applicant_read_obscure_attrs(self):
	# Applicant reading more obscure attributes in their own entry
	try:
	    res = self.ldap_applicant001.search_s(
		    ldap_applicant001DN,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['mozilliansVouchedBy','modifiersName','modifyTimestamp','userPassword'] )
        except ldap.LDAPError:
	    self.fail( "Applicant cannot search own entry " + str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'modifiersName'):
	    self.fail( "Applicant should see their own modifiersName value" )
	if not getAttrValue(res[0],'modifyTimestamp'):
	    self.fail( "Applicant should see their own modifyTimestamp value" )
	# There should not be a mozilliansVouchedBy value in an applicant entry!
	if getAttrValue(res[0],'mozilliansVouchedBy'):
	    self.fail( "Applicant should see their own mozilliansVouchedBy value" )
	# Should NOT see own password
	if getAttrValue(res[0],'userPassword'):
	    self.fail( "Applicant should not see their own userPassword value" )


    def test_T5010_mozillian_vouch_for_applicant(self):
        try:
	    self.ldap_mozillian011.modify_s(
		    ldap_applicant001DN,
		    [ (ldap.MOD_ADD,'mozilliansVouchedBy',ldap_mozillian011DN) ]
		)
        except ldap.LDAPError:
	    self.fail( "Mozillian cannot vouch for applicant " + str(sys.exc_info()[0]) )

    def test_T5010_mozillian_fake_vouch_for_applicant(self):
	# Mozillian should not be able to put someone else's DN into
	# an applicant's mozilliansVouchedBy attribute
        with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_mozillian011.modify_s(
		    ldap_applicant001DN,
		    [ (ldap.MOD_ADD,'mozilliansVouchedBy',ldap_applicant001DN) ]
		)

    def test_T5010_mozillian_unvouch_applicant(self):
	# Mozillian should not be able to remove any value from
	# an applicant's mozilliansVouchedBy attribute
        with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_mozillian011.modify_s(
		    ldap_applicant001DN,
		    [ (ldap.MOD_DELETE,'mozilliansVouchedBy',None) ]
		)

    def test_T5020_mozillian_fake_vouch_for_self(self):
	# Mozillian should not be able to modify
	# their own mozilliansVouchedBy attribute
        with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_mozillian011.modify_s(
		    ldap_mozillian011DN,
		    [ (ldap.MOD_ADD,'mozilliansVouchedBy',ldap_applicant001DN) ]
		)

    def test_T5020_applicant_fake_vouch_for_self(self):
	# Applicant should not be able to modify
	# their own mozilliansVouchedBy attribute
        with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_applicant001.modify_s(
		    ldap_applicant001DN,
		    [ (ldap.MOD_ADD,'mozilliansVouchedBy',ldap_applicant001DN) ]
		)

    def test_T5020_mozillian_fake_unvouch_self(self):
	# Mozillian should not be able to modify
	# their own mozilliansVouchedBy attribute
        with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_mozillian011.modify_s(
		    ldap_mozillian011DN,
		    [ (ldap.MOD_DELETE,'mozilliansVouchedBy',None) ]
		)

    def test_T5030_applicant_fake_vouch_for_another(self):
	# Applicant should not be able to modify
	# another applicant's mozilliansVouchedBy attribute
        with self.assertRaises(ldap.INSUFFICIENT_ACCESS):
	    self.ldap_applicant001.modify_s(
		    ldap_applicant002DN,
		    [ (ldap.MOD_ADD,'mozilliansVouchedBy',ldap_applicant001DN) ]
		)


    def test_T9010_uid_must_be_unique(self):
	# There is already an entry with uid=test002 in the test data
	# so we should not be able to change our own UID to clash
        with self.assertRaises(ldap.CONSTRAINT_VIOLATION):
	    self.ldap_mozillian011.modify_s(
	        ldap_mozillian011DN,
		    [
		        (ldap.MOD_REPLACE,'uid','test002'),
		    ]
		)


class LdapMonitorUserTests(unittest.TestCase):

    # These tests require a system user in the Monitor group
    #
    # Note also that most of the attributes we want are 'operational'
    # so we must request them by name
    # (or use the '*' '+' convention: OpenLDAP supports that, but some others don't)

    def setUp(self):
    	setUpCommon(self)
	# Add test user to group
	self.ldap_rootDN.modify_s(
		monitor_group,
		[ (ldap.MOD_ADD,'member',ldap_sys999DN) ]
	    )

    def tearDown(self):
	# Remove test user from group
	self.ldap_rootDN.modify_s(
		monitor_group,
		[ (ldap.MOD_DELETE,'member',ldap_sys999DN) ]
	    )
	# Now clear out test entries and close connections
    	tearDownCommon(self)

    def test_T8050_mozillian_snooping_on_stats(self):
        with self.assertRaises(ldap.NO_SUCH_OBJECT):
            self.ldap_mozillian011.search_s(monitor_suffix,ldap.SCOPE_BASE,'(objectclass=*)')
        with self.assertRaises(ldap.NO_SUCH_OBJECT):
            self.ldap_mozillian011.search_s(monitor_suffix,ldap.SCOPE_SUBTREE,'(objectclass=*)')

    def test_T8050_anon_snooping_on_stats(self):
        with self.assertRaises(ldap.NO_SUCH_OBJECT):
            self.ldap_anon.search_s(monitor_suffix,ldap.SCOPE_BASE,'(objectclass=*)')
        with self.assertRaises(ldap.NO_SUCH_OBJECT):
            self.ldap_anon.search_s(monitor_suffix,ldap.SCOPE_SUBTREE,'(objectclass=*)')

    def test_T8050_monitor_read_suffix(self):
        try:
	    res = self.ldap_sys999.search_s(
	            monitor_suffix,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['cn','monitoredInfo']
		)
        except ldap.LDAPError:
	    self.fail( "Monitor user cannot read "+monitor_suffix+" " + str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'cn'):
	    self.fail( "Monitor account should be able to see cn in cn=monitor" )
	if not getAttrValue(res[0],'monitoredInfo'):
	    self.fail( "Monitor account should be able to see monitoredInfo in cn=monitor" )

    def test_T8050_monitor_read_stats(self):
        try:
	    res = self.ldap_sys999.search_s(
	            'cn=Total,cn=Connections,'+monitor_suffix,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['monitorCounter','modifyTimestamp']
		    )
        except ldap.LDAPError:
	    self.fail( "Monitor user cannot read cn=Total,cn=Connections,"+monitor_suffix+" " +
	            str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'monitorCounter'):
	    self.fail( "Monitor account should be able to see monitorCounter" )
	if not getAttrValue(res[0],'modifyTimestamp'):
	    self.fail( "Monitor account should be able to see modifyTimestamp" )


class LdapReplicatorsUserTests(unittest.TestCase):

    # These tests require a system user in the Replicators group

    def setUp(self):
    	setUpCommon(self)
	# Add test user to group
	self.ldap_rootDN.modify_s(
		replicator_group,
		[ (ldap.MOD_ADD,'member',ldap_sys999DN) ]
	    )

    def tearDown(self):
	# Remove test user from group
	self.ldap_rootDN.modify_s(
		replicator_group,
		[ (ldap.MOD_DELETE,'member',ldap_sys999DN) ]
	    )
	# Now clear out test entries and close connections
    	tearDownCommon(self)

    def test_T7010_replicator_read_suffix(self):
        try:
	    res = self.ldap_sys999.search_s(
	            ldap_suffix,
		    ldap.SCOPE_BASE,
		    filterstr='(objectclass=*)',
		    attrlist=['*','+']
		)
        except ldap.LDAPError:
	    self.fail( "Replicator user cannot read "+ldap_suffix+" " + str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'objectclass'):
	    self.fail( "Replicator account should be able to see objectclass in suffix entry" )
	if not getAttrValue(res[0],'entryCSN'):
	    self.fail( "Replicator account should be able to see entryCSN in suffix entry" )

    def test_T7010_replicator_read_password(self):
	# This is the only account that should be able to read passwords
        try:
	    res = self.ldap_sys999.search_s(
	            ldap_suffix,
		    ldap.SCOPE_SUBTREE,
		    filterstr='(uid=test001)',
		    attrlist=['*','+']
		)
        except ldap.LDAPError:
	    self.fail( "Replicator user cannot find uid=test001" + str(sys.exc_info()[0]) )

	if not getAttrValue(res[0],'objectclass'):
	    self.fail( "Replicator account should be able to see objectclass in uid=test001 entry" )
	if not getAttrValue(res[0],'userPassword'):
	    self.fail( "Replicator account should be able to see userPassword in uid=test001 entry" )

    def test_T7020_replicator_read_dit(self):

	# WARNING: this will take a long time if run on a server with a lot of entries
	#          It may also cause memory exhaustion.
        try:
	    res = self.ldap_sys999.search_s(
	            ldap_suffix,
		    ldap.SCOPE_SUBTREE,
		    filterstr='(objectclass=*)',
		    attrlist=['*','+']
		    )
        except ldap.LDAPError:
	    self.fail( "Replicator user cannot enumerate the entire DIT " +
	            str(sys.exc_info()[0]) )

        # print "Got", len(res), "entries"

########################################################################
# Main program
########################################################################

if __name__ == '__main__':
    unittest.main()

