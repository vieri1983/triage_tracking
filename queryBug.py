#!/usr/bin/env python  
# encoding: utf-8  
 
import cookielib
import urllib2
import urllib
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import sys
import os
import psycopg2
import datetime
import time
from pyquery import PyQuery as pq
import argparse
 
__author__ = "Ming Li"
__copyright__ = "Copyright 2017, Ming Li, VMWare"
__credits__ = ["Ming Li"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Ming Li"
__email__ = "lming@vmware.com"
__status__ = "Production"


class Triage: 
    def __init__(self):
        self.DB='bugs'
        self.tb='tBugs'
        self.bugfile="id.txt"
        self.bkfile="bk.txt"
        #keep undetermined bugs in local file incase we restart service and lose all the current ones, its content is like '1\n2\n3\n'
        self.udfile=os.path.join(os.getcwd(),'udtm.txt')
        self.team=['ljhuang', 'Li Jun Huang', 'xiaotingm', 'Xiaoting (Shelley) Ma', 'lijin', 'Jin Li', 'btang', 'Bin Tang', 'emilyj', 'lming', 'Ming Li', 'bhou', 'Bei Hou', 'yancao', 'Yanhui Cao', 'gnie', 'Guoqiang Nie']
        self.queryLink='https://bugzilla.eng.vmware.com/buglist.cgi?cmdtype=runnamed&namedcmd=triaging&buglistsort=id,asc'
        self.user='lming'
        self.passwd='xxxxxxxx'
        self.table = None
        self.pt_table = None
        self.actRel = None
        self.email_body = None
        #item={"BUG_ID":"","SUMMARY":"","SEVERITY":"","PRIORITY":"","STATUS":"","ASSIGNEE":"","QA":"","PRODUCT":"","CATEGORY":"","COMPONENT":"","FIXBY":"","RESOLVEDATELONG":False,"TRIAGEDATELONG":False,"INCOMINGDATE":""}
        
        #if undetermined pool does not exist, create it
        if not os.path.isfile(self.udfile):
            print 'creating udtm pool'
            f = open(self.udfile, 'w')
            f.close()

        #try to connect to pre-built DB 'bugs', if fail, exit
        try:
            self.conn = psycopg2.connect("dbname='bugs' user='lming' host='127.0.0.1' password='111111'")
            print "DB connected"
        except Exception,e:
            print "exception:",e
            print "Fail to connect DB "
            sys.exit(1)
        #get the cursor for later usage
        self.cur=self.conn.cursor()
        
    def closeConn(self):
        self.cur.close()
        self.conn.close()
 

    def setup_cookie(self):
        cj = cookielib.CookieJar();
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj));
        urllib2.install_opener(opener);
    
     
    #login bugzilla
    def login_bugzilla(self):
        username = self.user
        password = self.passwd

        url = r'https://bugzilla.eng.vmware.com/index.cgi'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.99 Safari/537.36'
        }
     
        data = urllib.urlencode({"Bugzilla_login":username,"Bugzilla_password":password, "GoAheadAndLogIn":"Log In"})
        req = urllib2.Request(url, data, headers)
        response = urllib2.urlopen(req)
    
        the_page = response.read()
     
        #determin if we log in succeed
        if re.findall(r'Log out lming',the_page) != []:
            print 'login succeed!'
        else:
            print 'login failed~'
            sys.exit()
    
        response.close()
    

    #parse the searched page and return the buglist table in html
    def parse_querypage(self):
        #target_url='https://bugzilla.eng.vmware.com/buglist.cgi?cmdtype=runnamed&namedcmd=triaging&buglistsort=id,asc'
        target_url=self.queryLink
        res = urllib2.urlopen(target_url) 
        d = pq(res.read())
        d('table#buglistSorter').find('tr.itemBar').attr('class','w3-teal')
        t = d('table#buglistSorter').html()
        if t == None:
            #self.table = 'No new bugs today!'
            self.table = '<p style="font-size:200%;color:green;font-family:courier;">No new bugs today!</p>'
        else:
            t = re.sub(r'(show_bug.cgi\?id=\d+)',r'https://bugzilla.eng.vmware.com/\1',t)
            self.table = t

        #add triaging bugs to undertermined pool
        print 'updating udtm!'
        udtm=self.getUDlist()
        for bug in d('table#buglistSorter').find('tr')[1:]:     #skip first item tr
            bugID = bug.find('td')[0].text
            print 'we are judging bug: ', bugID
            if bugID not in udtm:
                self.addUD(bugID)

    #parse the pretriage searched page and return the buglist table in html
    def parse_pt_querypage(self):
        #target_url='https://bugzilla.eng.vmware.com/buglist.cgi?cmdtype=runnamed&namedcmd=pretriage'
        target_url='https://bugzilla.eng.vmware.com/buglist.cgi?cmdtype=runnamed&namedcmd=earlyEngage&buglistsort=id,asc#buglistsort=comp mgr,asc'
        res = urllib2.urlopen(target_url) 
        d = pq(res.read())

        t = d('table#buglistSorter').html()
        if t == None:
            #self.pt_table = 'No new bugs today!'
            self.pt_table = '<p style="font-size:200%;color:yellow;font-family:courier;">No new bugs today!</p>'
            return
 

        d('table#buglistSorter').find('tr.itemBar').attr('class','w3-teal')


        #add 'Info' column to the 1st of each row
        tooltip_th = '''
<th nowrap="nowrap">
Info
</th>
'''
        tooltip_td_head = '''
<td class="tooltip">>>
<span class="tooltiptext">
'''
        tooltip_td_tail = '''
</span>
</td>
'''

        d('table#buglistSorter').find('tr.w3-teal').prepend(tooltip_th)
        for tr in d('table#buglistSorter').find('tbody tr'):                         
            ID = pq(tr).find('td').eq(0).text()
            tooltip_text = self.fetch_info(ID)
            #tooltip_text = "Tooltip text"
            tooltip_td = tooltip_td_head + tooltip_text + tooltip_td_tail
            pq(tr).prepend(tooltip_td)


        t = d('table#buglistSorter').html()
        t = re.sub(r'(show_bug.cgi\?id=\d+)',r'https://bugzilla.eng.vmware.com/\1',t)

        self.pt_table = t

        
    #fulfill the tooltip_text to show information to users
    def fetch_info(self, ID):
        tooltip_text = "Tooltip text for bug: " + ID
        return tooltip_text

 
    
    def gen_email_body(self, table):
        header = '''
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    table, th, td {
        border: 1px solid black;
    }
    </style>
    </head>
    <body>
    
    <div>
        <p style="font-size:200%;color:blue;font-family:courier;">Click <a href="http://10.117.173.254:8080/">here</a> to see more statistics in Triage Home</p>
    </div>

    <table id="buglistSorter"
             class="bz_buglist tablesorter" cellspacing="0"
             cellpadding="4" width="100%">
    '''
        tail = '''
    </table>
    
    </body>
    </html>
    '''
        self.email_body = header + table + tail
    

    #send html format email
    def send_email(self):
        me = 'lming@mingrhel.com'
        to = 'lming@vmware.com'
        cc = 'qe-ljhuang-all@vmware.com'
        #cc = 'lming@vmware.com'
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Daily Triage Bugs"
        msg['From'] = me
        msg['To'] = to
        msg['CC'] = cc
        part = MIMEText(self.email_body.encode('utf-8'), 'html')
        msg.attach(part)
        s = smtplib.SMTP('localhost')
        s.sendmail(me, to, msg.as_string())
        s.quit()

     
    #parse one bug and return information we need
    def parse_bug(self, ID):
        target_url='https://bugzilla.eng.vmware.com/show_bug.cgi?id=%s' % ID
        res = urllib2.urlopen(target_url) 
        d = pq(res.read())
        #fetch bug ID
        title = d('head title').text()
        if title == 'Invalid Bug ID':
            print "Invalid Bug ID",ID
            return False
        
        item={"BUG_ID":"","SUMMARY":"","SEVERITY":"","PRIORITY":"","STATUS":"","ASSIGNEE":"","QA":"","PRODUCT":"","CATEGORY":"","COMPONENT":"","FIXBY":"","RESOLVEDATELONG":False,"TRIAGEDATELONG":False,"INCOMINGDATE":""}
        item["BUG_ID"] = title.split(u'\u2013')[0].replace('Bug ','',1)  #"Bug 1506383"
        #fetch summary
        item["SUMMARY"] = d('#bugSummary input').attr('value')
        #fetch bug PCC
        t=d('#bugPCC select').attr('onchange')
        for line in t.splitlines():
            if 'product' in line:
                item["PRODUCT"] = line.split('product:')[1].strip()[1:-2]
            if 'category' in line:
                item["CATEGORY"] = line.split('category:')[1].strip()[1:-2]
            if 'component' in line:
                item["COMPONENT"] = line.split('component:')[1].strip()[1:-2]
        #fetch status
        item["STATUS"] = d('#bugStatus span').text() 
        resolution = d('#bugResolution span').text()
        #fetch priority
        item["PRIORITY"] = d('#priority option:selected').text()
        #fetch severity
        item["SEVERITY"] = d('#bug_severity option:selected').text()
        #fetch assignee
        item["ASSIGNEE"] = d("#bugPeople label:contains('Assigned To')").siblings().text()
        #fetch qa contact
        item["QA"] = d("#bugPeople label:contains('QA Contact')").siblings().attr('value')
        #fetch fix by, if more than 1 fixby branch, find the 1st whose product in ['VMTools','vSphere']
        #row 0 is fixby lable, row 1 is template, we got row2 as the 1st fixby. Then we got column 1 and 2 to consist of fixby, phase omited.
        for fix in d('#fixByTable tr')[2:]:                                                  
            product=pq(fix).find('td').eq(0).children().find('option:selected').text()       
            if product in ['VMTools','vSphere']:                                             
                version=pq(fix).find('td').eq(1).children().find('input').attr('value')      
                item["FIXBY"] = product + ' ' + version
            else:       
                continue

        #check if bug was resolved for 14 days or longer
        if item["STATUS"] in ["closed", "resolved"] and resolution not in ['wont fix', 'duplicate', 'not a bug']:
            out = d("td.added:contains('resolved')").parent().parent().parent().siblings('.bz_comment_head').text()
            match=re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',out)
            resolve_date = match.group(1).split()[0]
            c=datetime.datetime.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")
            try:
                a=datetime.datetime.strptime(resolve_date, "%Y-%m-%d")
                item["RESOLVEDATELONG"] = (c-a > datetime.timedelta(14))
            except:
                pass

                
        #check if bug was triaged for 7 days or longer
        triage_date = ''
        out = d("td.added:contains('triaged')").parent().parent().parent().siblings('.bz_comment_head').text()
        if out != '':
            match=re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',out)
            triage_date = match.group(1).split()[0]
            c=datetime.datetime.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")
            try:
                a=datetime.datetime.strptime(triage_date, "%Y-%m-%d")
                item["TRIAGEDATELONG"] = (c-a > datetime.timedelta(7))
            except:
                pass

        #record incoming date. 1st try 'nominate' date, if no, try 'triaged' date, if no, set 'bug opened' date
        incoming_date = ''
        #out = d("td.added:contains('nominate')").parent().parent().parent().siblings('.bz_comment_head').text()
        out = d("td.added:contains('CheckinApprovalRequested')").parent().parent().parent().siblings('.bz_comment_head').text()
        if out != '':
            match=re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',out)
            incoming_date = match.group(1).split()[0]
        elif triage_date != '': #nominated date is NULL, which means it inherited from parent
            incoming_date = triage_date
        else: # triage date also NULL, use the 1st comment's date 
            out=d("div.bz_comment_head").eq(0).text()
            match=re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',out)
            incoming_date =  match.group(1).split()[0]
        item["INCOMINGDATE"] = incoming_date
                
 
        print item
        return item 

    def insertPR(self, ID):
        '''
        Insert one PR into DB/table one time
        '''
        #if bug_id already in DB, we just update it
        if self.inDB(ID):
            self.updatePR(ID)
            return

        item = self.parse_bug(ID)
        if not item:
            print "Error occured while adding PR %s" % ID
            return
        
        keys = item.keys()
        values = [ item[k] for k in keys ]
        sqlCommand = "INSERT INTO {tb} ({keys}) VALUES ({placeholders});".format(
        tb = self.tb,
        keys = ", ".join(keys),
        placeholders = ", ".join([ "%s" for v in values ])  # extra quotes may not be necessary
        )
        self.cur.execute(sqlCommand, values)
        self.conn.commit()
        print "Insert PR %s succeed!" % item["BUG_ID"]
        

    def insertMultiPR(self):
        f = open(self.bugfile,"r")
        for eachline in f:
            print eachline.strip()
            try:
                self.insertPR(eachline)
            except Exception,e:
                print "Exception :",e

        f.close()

    def updatePR(self, bugID):
        #bugID should exist in DB in advance
        if not self.inDB(bugID):
            return

        item = self.parse_bug(bugID)
        if not item:
            print "Error occured while updating PR %s" % bugID
            return
 
        keys = []
        values = []
        for k,v in item.iteritems():
            if k != "BUG_ID":
                keys.append(k)
                values.append(v)


        sqlCommand = "UPDATE %s SET %s where bug_id=%s" % (self.tb, ', '.join("%s = %%s" % u for u in keys), bugID)
        #sqlCommand = "UPDATE %s SET %s where id=%s" % (self.tb, ', '.join("%s = %%s" % u for u in keys),404)
        self.cur.execute(sqlCommand, values)
        self.conn.commit()
        print "Update PR %s succeed!" % bugID


    def updateDB(self):
        '''periodically update non-closed bugs information in DB'''
        db = self.selectNonClosedPR()
        for bug in db:
           self.updatePR(bug[1])

    def saveDB(self):
        '''save all the current bugs in DB to backup file'''
        f=open(self.bkfile,'w')
        db = self.selectPR()
        for bug in db:
            f.write(str(bug[1]))
            f.write('\n') 
        f.close()

    def selectNonClosedPR(self):
        sqlCommand = "SELECT * FROM {tb} WHERE STATUS not like 'closed';".format(
        #sqlCommand = "SELECT * FROM {tb};".format(
        tb = self.tb
        )
        self.cur.execute(sqlCommand)
        #note: fetchall get a dict list, whose 0th is id in DB, 1th start is as item
        return self.cur.fetchall()


    def selectPR(self):
        sqlCommand = "SELECT * FROM {tb} ORDER BY STATUS DESC,FIXBY,BUG_ID;".format(
        tb = self.tb
        )
        self.cur.execute(sqlCommand)
        #note: fetchall get a dict list, whose 0th is id in DB, 1th start is as item
        return self.cur.fetchall()

    def getNPR(self):
        '''
        get list of Number of PR Per Release
        return listNPR, whose 0th item is a list contains release name, 1st item is a list contains corresponding PR number
        '''
        listNPR = []
        listAxisX = []
        listAxisY = []
        sqlCommand = "select fixby, count(*) from tbugs group by fixby order by fixby;"
        self.cur.execute(sqlCommand)
        for each in self.cur.fetchall():
            listAxisX.append(each[0])
            listAxisY.append(int(each[1]))
        listNPR.append(listAxisX)
        listNPR.append(listAxisY)
        return listNPR
        

    def getNPC(self):
        '''
        get list of Number of PR Per Component 
        return listNPC, whose 0th item is a list contains product name, 1st item contains category name, 2nd item is a list contains corresponding PR number
        '''
        listNPC = []
        listAxisX = []
        listAxisY = []
        sqlCommand = "select product, category, count(*) from tbugs group by product,category order by product;"
        self.cur.execute(sqlCommand)
        for each in self.cur.fetchall():
            listAxisX.append(each[0]+":"+each[1])
            listAxisY.append(int(each[2]))
        listNPC.append(listAxisX)
        listNPC.append(listAxisY)
        return listNPC
 

    def getNPM(self):
        '''
        get list of Number of PR Per Month 
        return listNPM, whose 0th item is a list contains recent 12 months' name, 1st item is a list contains corresponding incoming PR number
        '''
        listNPM = []
        listAxisX = []
        listAxisY = []
        sqlCommand = "select to_char(incomingdate, 'YYYY-MM'),count(bug_id) from tbugs where incomingdate > (current_date - interval '12 months') group by to_char(incomingdate, 'YYYY-MM') order by to_char(incomingdate, 'YYYY-MM');"
        self.cur.execute(sqlCommand)
        for each in self.cur.fetchall():
            listAxisX.append(each[0])
            listAxisY.append(int(each[1]))
        listNPM.append(listAxisX)
        listNPM.append(listAxisY)
        return listNPM
 
    def inDB(self, ID):
        '''
        Return True if ID as bug_id exists in DB, False otherwise
        '''
        sqlCommand = "SELECT * FROM {tb} WHERE BUG_ID={bug_id};".format(
        tb = self.tb,
        bug_id = ID
        )
        self.cur.execute(sqlCommand)
        if self.cur.fetchall() != []:
            return True
        else:
            return False

    def deletePR(self, ID):
        sqlCommand = "DELETE FROM {tb} WHERE BUG_ID={bug_id};".format(
        tb = self.tb,
        bug_id = ID
        )
        self.cur.execute(sqlCommand)
        print "Delete PR %s succeed!" % ID
        

    def inTeam(self, person):
        return person in self.team

    def parseUndetermined(self, bugID):
        '''
        undetermined pool is necessary because when a bug was added 'triaged' kw, it will not be shown in triaging search
        then we should consider if add it in to DB or not. Before that, a bug was added in undetermined pool
        A bug has inherited kw 'triaged' from base bug, this is invalid. Because base bug should not add 'triaged' kw
        for each children. So we don't consider this situation. Every bug here should have been added 'triaged' in comments
        But given that many team add 'triaged' to base bug, we check 'CheckinApproved' kw instead. I modified query too.
        Therefore, QA has 3 states: in platformTeam, not in, not assigned(''). owner has 2: in platformTeam, not in.
        If owner in, add it to DB because we triaged it, we should track it and remove from undetermined. 
        Actually we will focus only on our own bugs in future, so there will be few bugs that we triage but we are not QA.
        If owner not in, consider QA.
        If QA in, add it to DB because we own it and remove from undetermined.
        If QA not in, remove it from undetermined and send me an email to double check. 
            If someone outside our team triaged bug for us, but he forgot changing QA to us, this will cause missing this bug. 
            So we must make sure to changing QA to correct team/person when triaging bugs.
        If QA not assigned yet, keep it in undetermined pool and wait for next parsing.
        RETURN value:
        > 0: insert it and remove from undetermined     
        < 0: discard it and remove from undetermined             
        = 0: keep it in undetermined                  
        '''
        target_url='https://bugzilla.eng.vmware.com/show_bug.cgi?id=%s' % bugID
        res = urllib2.urlopen(target_url) 
        d = pq(res.read())
        #verify bug ID is valid
        title = d('head title').text()
        if title == 'Invalid Bug ID':
            print "Invalid Bug ID",bugID
            return -1 
 
        #Maybe not triaged yet
        try:
            #owner = d("td.added:contains('triaged')").parent().parent().parent().siblings('.bz_comment_head').text().split('|')[1].strip()
            owner = d("td.added:contains('CheckinApproved')").parent().parent().parent().siblings('.bz_comment_head').text().split('|')[1].strip()
        except IndexError:
            print 'bug %s not triaged yet, keep it in UD' % bugID
            return 0
        
        QA = d("#bugPeople label:contains('QA Contact')").siblings().attr('value')
        print 'parsing bug: %s, owner: %s, QA: %s' % (bugID, owner, QA)

        #if owner == '', this is the situation that a bug inherited 'triaged' from base. Remove it.
        if owner == '':
            print 'bug %s inherited triaged keyword, remove it' % bugID
            return -1
        if self.inTeam(owner):
            print 'bug %s triaged by us, add it' % bugID
            return 1
        if not self.inTeam(owner):
            if self.inTeam(QA): 
                print 'bug %s owned by us, add it' % bugID
                return 1
            if not self.inTeam(QA):
                print 'bug %s neither triaged nor owned by us, remove it' % bugID
                return -1
            if QA == '':
                print 'bug %s not triaged by us, and QA not assigned yet, keep it in UD' % bugID
                return 0

    def getUDlist(self):
        '''
        get UnDeTerMined bug list
        '''
        udtm=[]
        with open(self.udfile, 'r') as f:
            for line in f:
                udtm.append(line.rstrip('\n'))
        print 'udtm:\n',udtm
        return udtm

    def addUD(self, bugID):
        '''
        Add a bug to undetermined pool
        '''
        print 'adding bug %s to undetermined pool!' % bugID
        f = open(self.udfile, 'a')
        f.write(bugID)
        f.write('\n')
        f.close()

    def removeUD(self, bugID):
        '''
        Remove a bug from undetermined pool
        '''
        print 'removing bug %s from undetermined pool!' % bugID
        udtm=self.getUDlist()
        f=open(self.udfile,'w')
        for bug in udtm:
            if bug != bugID:
                f.write(bug)
                f.write('\n')
        f.close()
 
    def updateUndetermined(self):
        '''
        Periodically called in backgroud to update the undetermined pool
        '''
        #read bug from undetermined pool
        print 'updating undetermined pool!'
        udtm = self.getUDlist()
        if udtm == []:
            return
        for bug in udtm:
            rt = self.parseUndetermined(bug)
            if rt > 0:
                self.insertPR(bug)
                self.removeUD(bug)
            if rt < 0:
                self.removeUD(bug)
            else:
                #stay the same
                continue                



                
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s","--saveDB", help="back up current DB", action="store_true")
    parser.add_argument("-r","--updateDB", help="update current DB", action="store_true")
    parser.add_argument("-m","--insertMultiPR", help="insert Multiple PR into DB, PR stored in ./id.txt", action="store_true")
    parser.add_argument("-i","--insertPR", help="insert a PR into DB")
    parser.add_argument("-u","--updatePR", help="update a PR in the DB")
    parser.add_argument("-l","--dummyMail", help="send a dummy mail to debug email function", action="store_true")
    args = parser.parse_args()
 

    triage = Triage()
    triage.setup_cookie()
 
    try:
        triage.login_bugzilla()
    except Exception, e:
        print 'fail to login bugzilla'
        print e
        sys.exit()

    if args.saveDB:
        print "let's back up DB to bk.txt now"
        triage.saveDB()
    elif args.updateDB:
        print "let's update DB now"
        triage.updateDB()
    elif args.insertMultiPR:
        print "let's insert PRs in id.txt" 
        triage.insertMultiPR()
    elif args.insertPR:
        print "let's insert this PR" ,args.insertPR
        triage.insertPR(args.insertPR)
    elif args.updatePR:
        print "let's update this PR" ,args.updatePR
        triage.updatePR(args.updatePR)
    elif args.dummyMail:
        print "let's only send a mail without other operation" 
        triage.parse_querypage()
        triage.gen_email_body(triage.table) 
        triage.send_email()
    else:
        #We take below actions periodically
        triage.updateUndetermined()
        triage.updateDB()
        triage.parse_querypage()
        triage.gen_email_body(triage.table) 
        triage.send_email()
        triage.saveDB()


    triage.closeConn()

    print 'ok'
 
if __name__=='__main__':
    main()
