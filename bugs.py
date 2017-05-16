#!/usr/bin/env python  
# encoding: utf-8  
 

""" Basic todo list using webpy 0.3 """
import web
import datetime
import time
import json
from queryBug import Triage


__author__ = "Ming Li"
__copyright__ = "Copyright 2017, Ming Li, VMWare"
__credits__ = ["Ming Li"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Ming Li"
__email__ = "lming@vmware.com"
__status__ = "Production"



### Url mappings

urls = (
    '/', 'Index',
    '/del/(\d+)', 'Delete',
    '/favicon.ico','Icon',
    '/pretriage', 'PreTriage'
)


### Templates
render = web.template.render('templates', base='base')

class Icon:
    def GET(self): 
        raise web.seeother("/static/favicon.ico")

class Index:
    def __init__(self):
        self.triage = Triage()
        self.triage.setup_cookie()
        try:
            self.triage.login_bugzilla()
        except Exception, e:
            print 'fail to login bugzilla'
            print e
            sys.exit()
     
        self.triage.parse_querypage()
        #try to get triage.email_body here
        self.triage.gen_email_body(self.triage.table) 
     
        self.form = web.form.Form(
            web.form.Textbox('Add bug:', web.form.notnull),
            web.form.Button('Submit'),
        )

    def GET(self):
        """ Show page """
        bugs = self.triage.selectPR()
        form = self.form()
        table = self.triage.table
        actRel = self.triage.actRel
        listNPR = self.triage.getNPR()
        listNPC = self.triage.getNPC()
        listNPM = self.triage.getNPM()
        return render.index(bugs, form, table, listNPR, listNPC, listNPM)

    def POST(self):
        """ Add new entry """
        form = self.form()
        if not form.validates():
            bugs = self.triage.selectPR()
            return render.index(bugs, form)
        self.triage.insertPR(form["Add bug:"].value)
        raise web.seeother('/')



class Delete:

    def POST(self, id):
        """ Delete based on ID """
        #id = int(id)
        self.triage.deletePR(id)
        raise web.seeother('/')

class PreTriage:
    def __init__(self):
        self.triage = Triage()
        self.triage.setup_cookie()
        try:
            self.triage.login_bugzilla()
        except Exception, e:
            print 'fail to login bugzilla'
            print e
            sys.exit()
     
        self.triage.parse_pt_querypage()

    def GET(self):
        """ Show page """
        pt_table = self.triage.pt_table
        return render.pretriage(pt_table)

app = web.application(urls, globals())

if __name__ == '__main__':
    app.run()
