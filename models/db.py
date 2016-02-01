# -*- coding: utf-8 -*-

#########################################################################
## This scaffolding model makes your app work on Google App Engine too
## File is released under public domain and you can use without limitations
#########################################################################

## if SSL/HTTPS is properly configured and you want all HTTP requests to
## be redirected to HTTPS, uncomment the line below:
# request.requires_https()

## app configuration made easy. Look inside private/appconfig.ini
from gluon.contrib.appconfig import AppConfig
## once in production, remove reload=True to gain full speed
myconf = AppConfig(reload=True)


if not request.env.web2py_runtime_gae:
    ## if NOT running on Google App Engine use SQLite or other DB
    db = DAL(myconf.take('db.uri'), 
        pool_size=10, 
        lazy_tables=True,
        migrate=True,
        migrate_enabled=True)
else:
    ## connect to Google BigTable (optional 'google:datastore://namespace')
    db = DAL('google:datastore+ndb')
    ## store sessions and tickets there
    session.connect(request, response, db=db)
    ## or store session in Memcache, Redis, etc.
    ## from gluon.contrib.memdb import MEMDB
    ## from google.appengine.api.memcache import Client
    ## session.connect(request, response, db = MEMDB(Client()))

## by default give a view/generic.extension to all actions from localhost
## none otherwise. a pattern can be 'controller/function.extension'
response.generic_patterns = ['*'] if request.is_local else []
## choose a style for forms
response.formstyle = myconf.take('forms.formstyle')  # or 'bootstrap3_stacked' or 'bootstrap2' or other
response.form_label_separator = myconf.take('forms.separator')

import logging
logger = logging.getLogger(request.application)
logger.setLevel(logging.DEBUG)

import os, logging.handlers
formatter="%(asctime)s %(filename)s:%(lineno)d %(funcName)s(): %(message)s"
handler = logging.handlers.RotatingFileHandler(os.path.join(request.folder,'private/app.log'),maxBytes=1024,backupCount=2)
handler.setFormatter(logging.Formatter(formatter))

handler.setLevel(logging.DEBUG)

logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

## (optional) optimize handling of static files
# response.optimize_css = 'concat,minify,inline'
# response.optimize_js = 'concat,minify,inline'
## (optional) static assets folder versioning
# response.static_version = '0.0.0'
#########################################################################
## Here is sample code if you need for
## - email capabilities
## - authentication (registration, login, logout, ... )
## - authorization (role based authorization)
## - services (xml, csv, json, xmlrpc, jsonrpc, amf, rss)
## - old style crud actions
## (more options discussed in gluon/tools.py)
#########################################################################

from gluon.tools import Auth, Service, PluginManager

auth = Auth(db)
service = Service()
plugins = PluginManager()

## create all tables needed by auth if not custom tables
auth.define_tables(username=True, signature=False)

## configure email
mail = auth.settings.mailer
mail.settings.server = 'logging' if request.is_local else myconf.take('smtp.server')
mail.settings.sender = myconf.take('smtp.sender')
mail.settings.login = myconf.take('smtp.login')

## configure auth policy
auth.settings.registration_requires_verification = True     # require verification of email address (email confirmation)
auth.settings.registration_requires_approval = False         # require admin to approve registrations
auth.settings.reset_password_requires_verification = True   # send email with link to reset password
auth.settings.create_user_groups="%(username)s"       # create group for user with group name same as username
auth.settings.everybody_group_id = 100                # everybody is part of the "all users group"

#########################################################################
## Define your tables below (or better in another model file) for example
##
## >>> db.define_table('mytable',Field('myfield','string'))
##
## Fields can be 'string','text','password','integer','double','boolean'
##       'date','time','datetime','blob','upload', 'reference TABLENAME'
## There is an implicit 'id integer autoincrement' field
## Consult manual for more options, validators, etc.
##
## More API examples for controllers:
##
## >>> db.mytable.insert(myfield='value')
## >>> rows=db(db.mytable.myfield=='value').select(db.mytable.ALL)
## >>> for row in rows: print row.id, row.myfield
#########################################################################
db.define_table('dbfile',
    Field('file_name', 'string', required=True),
    Field('file_type', 'string', requires=IS_IN_SET(['file','directory'])),
    Field('file_size', 'integer'),
    Field('file_owner', 'reference auth_user', requires=IS_EMPTY_OR(IS_IN_DB(db, 'auth_user.id', db.auth_user._format))),
    Field('file_parent', 'reference dbfile'),
    Field('file_children', 'list:reference dbfile', readable=False, writable=False),
    format='%(file_name)s'
    )

#db.person._after_delete.append(lambda s: pprint(s))
db.dbfile._before_delete.append(lambda s: before_delete_dbfile(s))
db.dbfile._after_insert.append(lambda f,id: after_insert_dbfile(f,id))
db.dbfile._before_update.append(lambda s, f: before_update_dbfile(s,f))
db.dbfile._after_update.append(lambda s, f: after_update_dbfile(s,f))

def before_update_dbfile(s,f):
    """
    check to make sure parent or children don't refer to themself.
    """
    logger.debug("before update called.  s: %s, f: %s" %(s,f))
    if f.get('file_parent'):
        if f.get('file_parent') == s.query.second:
            f['file_parent'] = None

    if f.get('file_children'):
        logger.debug('children present in update.  children: %s' %f.get('file_children'))
        if f.get('file_children').__contains__(str(s.query.second)):
            logger.debug('seems this is a child of itself.  stopping update')
            f.get('file_children').remove(str(s.query.second))

    return False

def after_insert_dbfile(f, id):
    """ 
    add this file as a child to the parent specified after insert

    we don't need to update any children of this record because it makes
    no sense we would have children before the parent exists.
    """
    logger.debug("after_insert callback called with record ID: %d record: %s" %(id, str(f)))
    if f.get('file_parent'):
        logger.debug('parent listed: %d.  Updating children of parent.', f.file_parent)
        children = db(db.dbfile.id == f.file_parent).select(db.dbfile.file_children).first().file_children
        if children == None:
            children = []
        children.append(id)
        db(db.dbfile.id == f.file_parent).update_naive(file_children=children)


def after_update_dbfile(s, f):
    """
    Update child & parent refs after update of a record.
    """
    this_file_id = s.query.second
    parent_id = db(db.dbfile.id==this_file_id).select(db.dbfile.file_parent).first().file_parent

    logger.debug('this_file_id: %d, parent_id: %d' %(this_file_id, parent_id))

    rowset = db((db.dbfile.file_children.contains(this_file_id)) & (db.dbfile.id != parent_id)).select()
    if rowset:
        logger.debug("parent changed for id: %d, new parent: %d, rowset: %s" %(this_file_id, parent_id, str(rowset)))
        for row in rowset:
            this_parent = row.id
            logger.debug('parent id: %d children before update: %s' %(this_parent, str(row)))
            children = row.file_children
            children.remove(this_file_id)
            logger.debug('parent id: %d children after update: %s' %(this_parent,str(children)))
            db(db.dbfile.id==this_parent).update_naive(file_children=children)

        logger.debug("updating new parent")
        parent_row = db(db.dbfile.id==parent_id).select().first()
        logger.debug('parent row: %s' %str(parent_row))
        parents_children = parent_row.file_children
        if parents_children == None:
            parents_children = []
        logger.debug('children before update: %s' %str(parents_children))
        parents_children.append(this_file_id)
        logger.debug('children after update: %s' %str(parents_children))
        db(db.dbfile.id==parent_id).update_naive(file_children=parents_children)

def before_delete_dbfile(s):
    """
    remove any children referring to this deleted row

    deleting a parent will automatically cascade.
    """
    logger.debug(s)
    logger.debug(s.select())
    for row in s.select():
        deleted_file_id = row.id

        ### Remove all children referenced to this file
        logger.debug("Removing all children references to ID: %d" %row.id)

        for update_row in db(db.dbfile.file_children.contains(deleted_file_id)).select():
            try:
                children = update_row.file_children
                logger.debug( "Old Children for ID: %d: %s" %(update_row.id, str(children)))
                children.remove(row.id)
                logger.debug( "New Children for ID: %d: %s" %(update_row.id, str(children)))
                db(db.dbfile.id == update_row.id).update_naive(file_children=children)
            except Exception, e:
                pass
    return None

## after defining tables, uncomment below to enable auditing
# auth.enable_record_versioning(db)
