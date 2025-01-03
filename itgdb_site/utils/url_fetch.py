"""Routines for fetching pack files from URLs.
"""

import os
import re
import urllib.request
import shutil
import uuid
from django.conf import settings
import gdown
from mega import Mega
from bs4 import BeautifulSoup


def _fetch_from_sm_online(url: str) -> str:
    req = urllib.request.Request(url)
    req.add_header(
        'User-Agent',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    )
    content = urllib.request.urlopen(req).read()
    soup = BeautifulSoup(content, 'html.parser')
    link = soup.find('a', string='Mirror')['href']
    assert link.startswith('/static/new/')
    return fetch_from_url('https://search.stepmaniaonline.net' + link)
    

def fetch_from_url(url: str) -> str:
    filename = str(uuid.uuid4())
    dir_path = str(settings.MEDIA_ROOT / 'packs')
    path = os.path.join(dir_path, filename)

    # fetch from google drive
    if re.match('https?://drive.google.com/', url):
        return gdown.download(url=url, output=path, fuzzy=True, quiet=True)

    # fetch from mega
    elif re.match('https?://mega.nz/', url):
        mega = Mega()
        m = mega.login()
        return str(m.download_url(url, dir_path, filename))
    
    # fetch from stepmaniaonline
    elif re.match('https?://search.stepmaniaonline.net/pack/id/', url):
        return _fetch_from_sm_online(url)
    
    # fetch from dropbox
    elif re.match('https?://www.dropbox.com/', url):
        # modify URL to so it can be fetched from directly
        url = url.replace('dl=0', 'dl=1')
    
    if url.startswith('http'):
        req = urllib.request.Request(url)
        req.add_header(
            'User-Agent',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
    else: # e.g. file://
        req = url
    with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)

    return path