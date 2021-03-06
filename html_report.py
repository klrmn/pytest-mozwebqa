#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import cgi
import httplib
import json
import os
import py
import time

from py.xml import html
from py.xml import raw


class HTMLReport(object):

    def __init__(self, config):
        logfile = os.path.expanduser(os.path.expandvars(config.option.webqa_report_path))
        self.logfile = os.path.normpath(logfile)
        self._debug_path = 'debug'
        self.config = config
        self.test_logs = []
        self.errors = self.failed = 0
        self.passed = self.skipped = 0
        self.xfailed = self.xpassed = 0

    def _debug_paths(self, testclass, testmethod):
        root_path = os.path.join(os.path.dirname(self.logfile), self._debug_path)
        root_path = os.path.normpath(os.path.expanduser(os.path.expandvars(root_path)))
        test_path = os.path.join(testclass.replace('.', '_'), testmethod)
        full_path = os.path.join(root_path, test_path)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        relative_path = os.path.join(self._debug_path, test_path)
        absolute_path = os.path.join(root_path, test_path)
        return (relative_path, full_path)

    def _appendrow(self, result, report):
        import pytest_mozwebqa
        (testclass, testmethod) = pytest_mozwebqa.split_class_and_test_names(report.nodeid)
        time = getattr(report, 'duration', 0.0)

        links = {}
        if hasattr(report, 'debug') and any(report.debug.values()):
            (relative_path, full_path) = self._debug_paths(testclass, testmethod)

            if report.debug['screenshots']:
                filename = 'screenshot.png'
                f = open(os.path.join(full_path, filename), 'wb')
                f.write(base64.decodestring(report.debug['screenshots'][-1]))
                links.update({'Screenshot': os.path.join(relative_path, filename)})

            if report.debug['html']:
                filename = 'html.txt'
                f = open(os.path.join(full_path, filename), 'wb')
                f.write(report.debug['html'][-1])
                links.update({'HTML': os.path.join(relative_path, filename)})

            # Log may contain passwords, etc so we only capture it for tests marked as public
            if report.debug['logs'] and 'public' in report.keywords:
                filename = 'log.txt'
                f = open(os.path.join(full_path, filename), 'wb')
                f.write(report.debug['logs'][-1])
                links.update({'Log': os.path.join(relative_path, filename)})

            if report.debug['network_traffic']:
                filename = 'networktraffic.json'
                f = open(os.path.join(full_path, filename), 'wb')
                f.write(report.debug['network_traffic'][-1])
                links.update({'Network Traffic': os.path.join(relative_path, filename)})

            if report.debug['urls']:
                links.update({'Failing URL': report.debug['urls'][-1]})

        if self.config.option.sauce_labs_credentials_file and hasattr(report, 'session_id'):
            links['Sauce Labs Job'] = 'http://saucelabs.com/jobs/%s' % report.session_id

        links_html = []
        for name, path in links.iteritems():
            links_html.append(html.a(name, href=path))
            links_html.append(' ')

        self.test_logs.append(
            html.tr(html.td(result,
                            class_=result.lower()),
                    html.td(testclass),
                    html.td(testmethod),
                    html.td(round(time)),
                    html.td(*links_html),
                    class_=result.lower()))

        if not 'Passed' in result:
            additional_html = []

            if self.config.option.sauce_labs_credentials_file and hasattr(report, 'session_id'):
                flash_vars = 'config={\
                    "clip":{\
                        "url":"http%%3A//saucelabs.com/jobs/%(session_id)s/video.flv",\
                        "provider":"streamer",\
                        "autoPlay":false,\
                        "autoBuffering":true},\
                    "plugins":{\
                        "streamer":{\
                            "url":"http://saucelabs.com/flowplayer/flowplayer.pseudostreaming-3.2.5.swf"},\
                        "controls":{\
                            "mute":false,\
                            "volume":false,\
                            "backgroundColor":"rgba(0, 0, 0, 0.7)"}},\
                    "playerId":"player%(session_id)s",\
                    "playlist":[{\
                        "url":"http%%3A//saucelabs.com/jobs/%(session_id)s/video.flv",\
                        "provider":"streamer",\
                        "autoPlay":false,\
                        "autoBuffering":true}]}' % {'session_id': report.session_id}

                additional_html.append(
                    html.div(
                        html.object(
                            html.param(value='true',
                                       name='allowfullscreen'),
                            html.param(value='always',
                                       name='allowscriptaccess'),
                            html.param(value='high',
                                       name='quality'),
                            html.param(value='true',
                                       name='cachebusting'),
                            html.param(value='#000000',
                                       name='bgcolor'),
                            html.param(value=flash_vars.replace(' ', ''),
                                       name='flashvars'),
                            width='100%',
                            height='100%',
                            type='application/x-shockwave-flash',
                            data='http://saucelabs.com/flowplayer/flowplayer-3.2.5.swf?0.2566397726976729',
                            name='player_api',
                            id='player_api'),
                        id='player%s' % report.session_id,
                        class_='video'))

            if 'Screenshot' in links:
                additional_html.append(
                    html.div(
                        html.a(html.img(src=links['Screenshot']),
                               href=links['Screenshot']),
                        class_='screenshot'))

            if report.longrepr:
                log = html.div(class_='log')
                for line in str(report.longrepr).splitlines():
                    separator = line.startswith('_ ' * 10)
                    if separator:
                        log.append(line[:80])
                    else:
                        exception = line.startswith("E   ")
                        if exception:
                            log.append(html.span(raw(cgi.escape(line)),
                                                 class_='error'))
                        else:
                            log.append(raw(cgi.escape(line)))
                    log.append(html.br())
                additional_html.append(log)

            self.test_logs.append(
                html.tr(
                    html.td(*additional_html,
                            colspan='5')))

    def _make_report_dir(self):
        logfile_dirname = os.path.dirname(self.logfile)
        if logfile_dirname and not os.path.exists(logfile_dirname):
            os.makedirs(logfile_dirname)
        return logfile_dirname

    def _send_result_to_sauce(self, report):
        if hasattr(report, 'session_id'):
            try:
                result = {'passed': report.passed or (report.failed and 'xfail' in report.keywords)}
                credentials = _credentials(self.config.option.sauce_labs_credentials_file)
                basic_authentication = ('%s:%s' % (credentials['username'], credentials['api-key'])).encode('base64')[:-1]
                connection = httplib.HTTPConnection('saucelabs.com')
                connection.request('PUT', '/rest/v1/%s/jobs/%s' % (credentials['username'], report.session_id),
                                   json.dumps(result),
                                   headers={'Authorization': 'Basic %s' % basic_authentication,
                                            'Content-Type': 'text/json'})
                connection.getresponse()
            except:
                pass

    def append_pass(self, report):
        self.passed += 1
        self._appendrow('Passed', report)

    def append_failure(self, report):
        if "xfail" in report.keywords:
            self._appendrow('XPassed', report)
            self.xpassed += 1
        else:
            self._appendrow('Failed', report)
            self.failed += 1

    def append_error(self, report):
        self._appendrow('Error', report)
        self.errors += 1

    def append_skipped(self, report):
        if "xfail" in report.keywords:
            self._appendrow('XFailed', report)
            self.xfailed += 1
        else:
            self._appendrow('Skipped', report)
            self.skipped += 1

    def pytest_runtest_logreport(self, report):
        if self.config.option.sauce_labs_credentials_file:
            self._send_result_to_sauce(report)

        if report.passed:
            if report.when == 'call':
                self.append_pass(report)
        elif report.failed:
            if report.when != "call":
                self.append_error(report)
            else:
                self.append_failure(report)
        elif report.skipped:
            self.append_skipped(report)

    def pytest_sessionstart(self, session):
        self.suite_start_time = time.time()

    def pytest_sessionfinish(self, session, exitstatus, __multicall__):
        self._make_report_dir()
        logfile = py.std.codecs.open(self.logfile, 'w', encoding='utf-8')

        suite_stop_time = time.time()
        suite_time_delta = suite_stop_time - self.suite_start_time
        numtests = self.passed + self.failed + self.xpassed + self.xfailed

        server = self.config.option.sauce_labs_credentials_file and \
                 'Sauce Labs' or 'http://%s:%s' % (self.config.option.host, self.config.option.port)
        browser = self.config.option.browser_name and \
                  self.config.option.browser_version and \
                  self.config.option.platform and \
                  '%s %s on %s' % (str(self.config.option.browser_name).title(),
                                   self.config.option.browser_version,
                                   str(self.config.option.platform).title()) or \
                  self.config.option.environment or \
                  self.config.option.browser

        configuration = {
            'Base URL': self.config.option.base_url,
            'Build': self.config.option.build,
            'Selenium API': self.config.option.api,
            'Driver': self.config.option.driver,
            'Firefox Path': self.config.option.firefox_path,
            'Google Chrome Path': self.config.option.chrome_path,
            'Selenium Server': server,
            'Browser': browser,
            'Timeout': self.config.option.timeout,
            'Capture Network Traffic': self.config.option.capture_network,
            'Credentials': self.config.option.credentials_file,
            'Sauce Labs Credentials': self.config.option.sauce_labs_credentials_file}

        doc = html.html(
            html.head(
                html.title('Test Report'),
                html.style(
                    'body {font-family: Helvetica, Arial, sans-serif; font-size: 12px}\n',
                    'body * {box-sizing: -moz-border-box; box-sizing: -webkit-border-box; box-sizing: border-box}\n',
                    'a {color: #999}\n',
                    'h2 {font-size: 16px}\n',
                    'table {border: 1px solid #e6e6e6; color: #999; font-size: 12px; border-collapse: collapse}\n',
                    '#configuration tr:nth-child(odd) {background-color: #f6f6f6}\n',
                    '#results {width:100%}\n',
                    'th, td {padding: 5px; border: 1px solid #E6E6E6; text-align: left}\n',
                    'th {font-weight: bold}\n',
                    'tr.passed, tr.skipped, tr.xfailed, tr.error, tr.failed, tr.xpassed {color: inherit}\n'
                    'tr.passed + tr.additional {display: none}\n',
                    '.passed {color: green}\n',
                    '.skipped, .xfailed {color: orange}\n',
                    '.error, .failed, .xpassed {color: red}\n',
                    '.log:only-child {height: inherit}\n',
                    raw('.log {background-color: #e6e6e6; border: 1px solid #e6e6e6; color: black; display: block; font-family: "Courier New", Courier, monospace; height: 230px; overflow-y: scroll; padding: 5px; white-space:pre-wrap}\n'),
                    '.screenshot, .video {border: 1px solid #e6e6e6; float:right; height:240px; margin-left:5px; overflow:hidden; width:320px}\n',
                    '.screenshot img {width: 320px}')),
            html.body(
                html.h2('Configuration'),
                html.table(
                    [html.tr(html.td(k), html.td(v)) for k, v in sorted(configuration.items()) if v],
                    id='configuration'),
                html.h2('Summary'),
                html.p(
                    '%i tests ran in %i seconds.' % (numtests, suite_time_delta),
                    html.br(),
                    html.span('%i passed' % self.passed, class_='passed'), ', ',
                    html.span('%i skipped' % self.skipped, class_='skipped'), ', ',
                    html.span('%i failed' % self.failed, class_='failed'), ', ',
                    html.span('%i errors' % self.errors, class_='error'), '.',
                    html.br(),
                    html.span('%i expected failures' % self.xfailed, class_='skipped'), ', ',
                    html.span('%i unexpected passes' % self.xpassed, class_='failed'), '.'),
                html.h2('Results'),
                html.table(
                    html.tr(html.th('Result'),
                            html.th('Class'),
                            html.th('Name'),
                            html.th('Duration'),
                            html.th('Links')),
                    *self.test_logs,
                    id='results')))

        logfile.write(doc.unicode(indent=2))
        logfile.close()
