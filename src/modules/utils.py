#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Copyright 2016 Fedele Mantuano (https://twitter.com/fedelemantuano)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import unicode_literals
import copy
import datetime
import hashlib
import logging
import os
import ssdeep
import yaml
from .exceptions import ImproperlyConfigured

log = logging.getLogger(__name__)


class MailItem(object):
    def __init__(
        self,
        filename,
        mail_server='localhost',
        mailbox='localhost',
        priority=None,
        trust=None,
    ):
        self.filename = filename
        self.mail_server = mail_server
        self.mailbox = mailbox
        self.priority = priority
        self.trust = trust
        self.timestamp = os.path.getctime(filename)

    def __cmp__(self, other):
        if self.priority > other.priority:
            return 1
        if self.priority < other.priority:
            return -1

        if self.timestamp > other.timestamp:
            return 1
        if self.timestamp < other.timestamp:
            return -1

        return 0


def fingerprints(data):
    # md5
    md5 = hashlib.md5()
    md5.update(data)
    md5 = md5.hexdigest()

    # sha1
    sha1 = hashlib.sha1()
    sha1.update(data)
    sha1 = sha1.hexdigest()

    # sha256
    sha256 = hashlib.sha256()
    sha256.update(data)
    sha256 = sha256.hexdigest()

    # sha512
    sha512 = hashlib.sha512()
    sha512.update(data)
    sha512 = sha512.hexdigest()

    # ssdeep
    ssdeep_ = ssdeep.hash(data)

    return md5, sha1, sha256, sha512, ssdeep_


def search_words_in_text(text, keywords):
    """Given a list of words return True if one or more
    lines are in text, else False.
    keywords format:
        keywords = [
            "word1 word2",
            "word3",
            "word4",
        ]
    (word1 AND word2) OR word3 OR word4
    """

    text = text.lower()

    for line in keywords:
        count = 0
        words = line.lower().split()

        for w in words:
            if w in text:
                count += 1

        if count == len(words):
            return True

    return False


def load_config(config_file):
    try:
        with open(config_file, 'r') as c:
            return yaml.load(c)
    except:
        message = "Config file {} not loaded".format(config_file)
        log.exception(message)
        raise ImproperlyConfigured(message)


def reformat_output(mail=None, bolt=None, **kwargs):
    """ This function replaces the standard SpamScope JSON output.
    The output is splitted in two parts: mail and attachments.
    In mail part are reported only the hashes of attachments.
    In attachments part the archived files are reported in root with the
    archive files.

    Args:
        mail (dict): raw SpamScope output
        bolt (string): only bolt can reformat the output
        kwargs:
            elastic_index_mail: prefix of Elastic index for mails
            elastic_index_attach: prefix of Elastic index for attachments
            elastic_type_mail: prefix of Elastic doc_type for mails
            elastic_type_attach: prefix of Elastic doc_type for attachments

    Returns:
        (mail, attachments):
            mail (dict): Python object with mail details
            attachments(list): Python list with all attachments details
    """

    if bolt not in ('output-elasticsearch', 'output-redis'):
        message = "Bolt '{}' not in list of permitted bolts".format(bolt)
        log.exception(message)
        raise ImproperlyConfigured(message)

    if mail:
        mail = copy.deepcopy(mail)
        attachments = []

        if bolt == "output-elasticsearch":
            # Date for daily index
            try:
                timestamp = datetime.datetime.strptime(
                    mail['analisys_date'], "%Y-%m-%dT%H:%M:%S.%f")
            except:
                # Without microseconds
                timestamp = datetime.datetime.strptime(
                    mail['analisys_date'], "%Y-%m-%dT%H:%M:%S")

            mail_date = timestamp.strftime("%Y.%m.%d")

        # Get a copy of attachments
        raw_attachments = []
        if mail.get("attachments", []):
            raw_attachments = copy.deepcopy(mail["attachments"])

        # Prepair attachments for bulk
        for i in raw_attachments:
            i['is_archived'] = False

            if bolt == "output-elasticsearch":
                i['@timestamp'] = timestamp
                i['_index'] = kwargs['elastic_index_attach'] + mail_date
                i['_type'] = kwargs['elastic_type_attach']
                i['type'] = kwargs['elastic_type_attach']

            for j in i.get("files", []):
                f = copy.deepcopy(j)

                # Prepair archived files
                f['is_archived'] = True

                if bolt == "output-elasticsearch":
                    f['@timestamp'] = timestamp
                    f['_index'] = kwargs['elastic_index_attach'] + mail_date
                    f['_type'] = kwargs['elastic_type_attach']
                    f['type'] = kwargs['elastic_type_attach']

                attachments.append(f)

                # Remove from archived payload, virustotal and thug
                # now in root
                j.pop("payload", None)
                j.pop("virustotal", None)
                j.pop("thug", None)

            attachments.append(i)

        # Remove from mail the attachments huge fields like payload
        # Fetch from Elasticsearch more fast
        for i in mail.get("attachments", []):
            i.pop("payload", None)
            i.pop("tika", None)
            i.pop("virustotal", None)
            i.pop("thug", None)

            for j in i.get("files", []):
                j.pop("payload", None)
                j.pop("virustotal", None)
                j.pop("thug", None)

        # Prepair mail for bulk
        if bolt == "output-elasticsearch":
            mail['@timestamp'] = timestamp
            mail['_index'] = kwargs['elastic_index_mail'] + mail_date
            mail['type'] = kwargs['elastic_type_mail']
            mail['_type'] = kwargs['elastic_type_mail']

        return mail, attachments
