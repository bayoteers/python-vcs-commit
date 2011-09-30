#! /usr/bin/python

import sys, netrc, urllib, os

from optparse import OptionParser
from datetime import datetime
from ConfigParser import ConfigParser

from minideblib.DpkgChangelog import DpkgChangelogEntry, DpkgChangelog
from bugzillarest import BugzillaREST

class VCStoBugzilla():
    """
    An easy way to process debian changelog messages from git/hg/svn and commit them to Bugzilla

    Either comment only or resolve/fix a bug if specific keywords are present
    """

    def __init__(self, options):
        """
        Initialization and check of the options
        
        :param options: an object that holds all the info needed for the hook to proceed
        :type options: class

        options needs to have all these properties

        :param bugzilla: The bugzilla server URL (without the rest uri)
        :type bugzilla: string
        :param rest_uri: The REST part of the url
        :type rest_uri: string
        :param chglog: The changelog message (extracted from debian/changelog)
        :type chglog: string
        :param commentonly: Do only comment
        :type commentonly: bool
        :param msg: The commit message
        :type msg: string
        :param netrc: The netrc file location
        :type netrc: string
        :param proxy: Overrides the proxy in case you don't like the ENV one
        :type proxy: string
        :param rev: The revision number / commit hash
        :type rev: string
        :param tm: Whether to add the target milestone to the bug (as the current week)
        :type tm: bool
        :param user: The user that did the commit (coming from the VCS)
        :type user: string
        :param vcstype: What VCS are we working with (HG/GIT/SVN)
        :type vcstype: string
        :param vcsurl: the base url of the VCS (this is not trivial to guess, look at the code)
        :type vcsurl: string
        """
        supported_vcstypes = ['hg', 'git', 'trac', 'svn']
        if options.vcstype not in supported_vcstypes:
            print >> sys.stderr, "Unsupported vcs type. Supported types are %s " % supported_vcstypes
        self.options = options
        self.config = self.parse_config()
        if self.options.vcstype == 'svn':
            self.finalurl = os.path.join(self.options.vcsurl, self.config['svn_commiturl'], self.options.rev)
        elif self.options.vcstype == 'git':
            self.finalurl = self.options.vcsurl + self.config['git_commit_url'] % self.options.rev
        elif self.options.vcstype == 'hg':
            self.finalurl = os.path.join(self.options.vcsurl, self.config['hg_commit_url'], '%s' % self.options.rev)
        elif self.options.vcstype == 'trac':
            from trac.env import open_environment
            env = open_environment(self.options.vcsurl)
            self.finalurl = os.path.join(env.config.get('project', 'url'), self.config['trac_commit_url'], self.options.rev)
        else:
            print >> sys.stderr, 'Configuration is not complete: please check the options passed'
            sys.exit(1)

        if self.options.tm:
            year, week = datetime.now().isocalendar()[0:2]
            self.target_milestone = '%d-%02d' % (year, week)
        else:
            self.target_milestone = None
        self.open_statuses = [ 'NEW', 'ASSIGNED', 'REOPENED', 'WAITING', 'NEED_INFO' ]

    def parse_config(self):
        """
        Reads the config file (default in /etc/vcscommit/vcscommit.cfg

        :rtype: ConfigParser object
        """
        cfg = ConfigParser()
        cfg.read('/etc/vcscommit/vcscommit.cfg')
        return cfg.defaults()

    def validate_login(self, url, netrcfile=None):
        """
        Takes username and pwd from netrc file

        :param url: the url we are authenticating to
        :type url: string
        :param netrcfile: the location of the netrc file
        :type netrcfile: string
        """
        base_host = urllib.splithost(urllib.splittype(url)[1])[0]
        # Try to grab authenticators out of your .netrc
        try:
            name, account, password = netrc.netrc(netrcfile).authenticators(base_host)
        except:
            raise SystemExit("You must have valid ~/.netrc for host %s" % base_host)

        return name, account, password

    def work_the_bug(self, bugs, message):
        """
        Does the actual comment on a set of bugs with the given message

        :param bugs: List of bugs to work on
        :type bugs: list
        :param message: Message to write on the bug
        :type message: string
        """
        for bug in bugs:
            retries = 0
            res = False
            while not res and retries <= 3:
                if retries > 0:
                    print sys.stdout, "Something went wrong with Bugzilla retrying (%s)" % retries
                if not self.options.commentonly:
                    res = bug.resolve(message, 'fixed', self.target_milestone)
                else:
                    res = bug.comment(message)
                retries += 1

            if not res:
                print >> sys.stdout, "Sorry we failed to update bug %s" % bug.id
                print >> sys.stderr, res
            else:
                print >> sys.stdout, "Bug #%s processed" % bug.id

    def process_entry(self, entry):
        """
        Process one entry in the changelog
        
        :param entry: The changelog entry
        :type entry: DpkgChangelogEntry object
        """

        if entry.nbugsfixed:
            name, account, password = self.validate_login(self.options.bugzilla, self.options.netrc)

            bugzilla = {'base_url': self.options.bugzilla,
                        'rest_uri': self.options.rest_uri,
                        'user': name,
                        'passwd': password}
            if self.options.proxy:
                session = BugzillaREST(bugzilla, self.options.proxy)
            else:
                session = BugzillaREST(bugzilla)

            bugs = session.get_many(entry.nbugsfixed)
            
            if not self.options.commentonly:
                action = 'Fixed'
            else:
                action = 'Commented'

            if entry.package:
                package = "package %s" % entry.package
            else:
                package = ""

            if entry.version:
                version = package + " (%s)" % entry.version.__str__()
            else:
                version = package

            msg_tmpl = '%(action)s as %(user)s submitted %(ver)s:\n'\
                       '%(url)s\n'\
                       'Commit message:\n'\
                       '%(msg)s\n'\
                       '%(chglog)s'
            # Write a different changelog per each bug
            # with relevant information only
            if bugs:
                if self.options.chglog:
                    for bug in bugs:
                        if bug.info.status not in self.open_statuses:
                            print "Bug #%s is in %s status... doing nothing" % (bug.id, bug.info.status)
                            continue
                        for chglog_entry in entry.entries:
                            if chglog_entry.find(str(bug.id)) != -1:
                                the_changelog = "Relevant changelog message:\n%s" % chglog_entry 
                                message = msg_tmpl % {
                                        'ver': version,
                                        'action': action,
                                        'user': self.options.user,
                                        'url' : self.finalurl,
                                        'msg' : self.options.msg,
                                        'chglog' : the_changelog    
                                        }
                                self.work_the_bug([bug], message)    
                                break
                else:
                    the_changelog = ''
                    message = msg_tmpl % {
                        'ver': version,
                        'action': action,
                        'user': self.options.user,
                        'url' : self.finalurl,
                        'msg' : self.options.msg,
                        'chglog' : the_changelog    
                        }
                    self.work_the_bug(bugs, message)    
            
    def run(self):
        """
        Runs the business
        """
        entry = DpkgChangelogEntry()
        for aline in self.options.msg.split('\n'):
            entry.add_entry(aline)


        if self.options.chglog:
            # If we have the changelog we prefer 
            # to use this instead of the commit msg
            ch = DpkgChangelog()
            ch.parse_changelog(self.options.chglog)
            for oneentry in ch.entries:
                self.process_entry(oneentry)
        else:
            self.process_entry(entry)
        

def main():
    parser = OptionParser()
    parser.add_option('-t', '--trac', dest='trac', help='Path to the Trac project')
    parser.add_option('-G', '--git', help='Git url (used for dvcs) conflicts with -U and -H')
    parser.add_option('-H', '--hg', help='HG url (used for dvcs) conflicts with -U and -G')#
    parser.add_option('-U', '--url', dest='url', help='URL to use in changeset references')
    parser.add_option('-r', '--revision', dest='rev', help='Repository revision number')
    parser.add_option('-u', '--user', dest='user', help='The user who is responsible for this action')
    parser.add_option('-m', '--msg', dest='msg', help='The log message to search')
    parser.add_option('-c', '--encoding', dest='encoding', help='The encoding used by the log message')
    parser.add_option('-b', '--bugzilla', dest='bugzilla', help='Bugzilla base URL')
    parser.add_option('--rest', dest='rest_uri', help='Bugzilla REST uri (the .._rest part of the URL')
    parser.add_option('-P', '--proxy', dest='proxy', help='Proxy server address')
    parser.add_option('-n', '--netrc', dest='netrc', default=None, help='Netrc file name')
    parser.add_option('--chglog', dest='chglog', default=None, help='here goes the whole changelog from debian/changelog')
    parser.add_option('--tm', dest='tm', action="store_true", default=False, help='Set target milestone when closing')
    parser.add_option('--commentonly', action="store_true", default=False, help='Comment only, don\'t resolve the bug')

    options, args = parser.parse_args()

    if (options.url and options.git) or (options.git and options.trac) or (options.url and options.trac) or (options.url and options.hg) or (options.hg and options.trac) or (options.hg and options.git):
        print >> sys.stderr, 'Conflict in -U and -G options or -G and -t or -t and -U or -U and -H or -H and it or -H and -G'
        sys.exit(1)


    if not options.bugzilla or not options.rest_uri:
        print >> sys.stderr, "You need to provide a bugzilla url with a --rest uri"
        sys.exit(1)

    # from trac.util.text import to_unicode
    #msg = to_unicode(options.msg, options.encoding)

    VCStoBugzilla(options).run()
    
    if options.url:
        options.vcstype = 'svn'
        options.vcsurl = options.url
    elif options.git:
        options.vcstype = 'git'
        options.vcsurl = options.git
    elif options.hg:
        options.vcstype = 'hg'
        options.vcsurl = options.hg
    elif options.trac:
        options.vcstype = 'trac'
        options.vcsurl = options.trac



if __name__ == '__main__':
    main()

# vim:ts=4:sw=4:et
