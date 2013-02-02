import time
import PIL
import urllib2
import requests
import threading
import HTMLParser
from django.http import HttpResponse, HttpResponseBadRequest
from htmlentitydefs import entitydefs
import json
import msgpack

from pyquery import PyQuery as pq

from django.views.decorators.cache import cache_page

def format(f):
    def newf(request, *args, **kwargs):
        if 'page' in kwargs:
            kwargs['page'] = int(kwargs['page'])
        format_ = 'json'
        if 'format' in request.GET:
            format_ = request.GET['format']
        if format_ == 'json':
            serializer = json.dumps
            mime = 'application/json'
        elif format_ == 'msgpack':
            serializer = msgpack.packb
            mime = 'application/x-msgpack'
        else:
            return HttpResponseBadRequest(
                    'Valid formats are json and msgpack, not %s' % format_)
        return HttpResponse(serializer(f(request, *args, **kwargs)), mimetype=mime)
    return newf

def entity2unicode(text):
    for (entity, iso) in entitydefs.iteritems():
        text = text.replace('&%s;' % entity, iso.decode('iso-8859-1'))
    return text

def recursive_comment_encoder(comments, encoding):
    for comment in comments:
        comment['content'] = comment['content'].encode(encoding)
        recursive_comment_encoder(comment['replies'], encoding)

unescape = HTMLParser.HTMLParser().unescape

############

SITES = {
        'dtc': 'Dans ton chat',
        'pebkac': 'Pebkac',
        'vdm': 'Vie de merde',
        'fml': 'Fuck my life',
        'bash': 'bash.org',
        'xkcd': 'xkcd',
        }
FIELDS = ['site', 'mode', 'type', 'page', 'id']

@format
def list_sites(request):
    return [{'id': x, 'name': y} for (x,y) in SITES.iteritems()]


@format
def state_url(request):
    """Takes a client state as GET parameters, and returns an URL."""
    state = dict(request.GET)

    # Check all fields are known
    unknown_fields = [x for x in state if x not in FIELDS]
    if len(unknown_fields) != 0:
        return {'status': 'error', 'message': 'Unknown field.',
                'data': unknown_fields}

    # Check no field is duplicated
    duplicated_fields = [x for x,y in state.iteritems() if len(y) > 1]
    if len(duplicated_fields) != 0:
        return {'status': 'error', 'message': 'Duplicated field.',
                'data': duplicated_fields}
    # No field is duplicated, so all lists are singletons.
    state = dict([(x, y[0]) for (x,y) in state.iteritems()])

    # Check the site is valid
    if 'site' not in state:
        return {'status': 'error', 'message': 'Missing fields.',
                'data': ['site']}
    if state['site'] not in SITES:
        return {'status': 'error', 'message': 'No \'%s\' is not a valid site.'%
                state['site']}

    # Default value for the mode
    if 'mode' not in state:
        state['mode'] = 'latest'

    url = '/%s/quotes/%s/' % (state['site'], state['mode'])

    # Handle different 'top' fields selection for fml and vdm
    if state['site'] in ('vdm', 'fml') and state['mode'] == 'top':
        if 'type' not in state or state['type'] is None or \
                state['type'] == 'null':
            state['type'] = 'week'
        if state['type'] != 'ever':
            url += '%s/' % state['type']
    state['site_id'] = state['site']
    state['site_name'] = SITES[state['site']]

    if state['mode'] == 'show':
        if 'id' not in state:
            return {'status': 'error', 'message': 'Missing fields.',
                    'data': ['id']}
        if len(state):
            return {'status': 'error', 'message': 'Some fields are not relevant',
                    'data': [x for x in state if x != 'id']}
        url += '%s/' % state['id']
    else:
        if 'id' in state:
            return {'status': 'error', 'message': 'Some fields are not relevant.',
                    'data': ['id']}

    # Append the page number, if any
    if state['mode'] not in ('top', 'random') and 'page' in state:
        url += '%s/' % state['page']

    return {'status': 'ok', 'url': url, 'state': state}

############

def vdmfml_parse_list(url):
    d = pq(url=url)
    messages = [pq(x) for x in d('div.post.article')]
    results = []
    for message in messages:
        link = message('div.date div.left_part a')
        id_ = int(link.text()[1:])
        quote_url = 'https://' + url.split('/')[2] + link.attr('href')
        content = ''.join([x.text or '' for x in message('a.fmllink')])
        up = int(message('div.date div.right_part span.dyn-vote-j-data').text())
        down = int(message('div.date div.right_part span span.dyn-vote-t-data').text())
        results.append({'id': id_, 'content': entity2unicode(content),
            'up': up, 'down': down, 'url': quote_url})
    return results

def vdmfml_show(quote_url, comments_url, id_):
    id_ = int(id_)
    d = pq(url=quote_url % id_)
    quote = pq(d('div.post.article'))
    content = ''.join([x.text for x in quote('a.fmllink')])
    up = int(quote('span.dyn-vote-j-data').text())
    down = int(quote('span.dyn-vote-t-data').text())
    (date, category, author) = quote('div.right_part p').next().text().split(' - ', 2)
    quote = {'id': id_, 'content': entity2unicode(content),
        'author': author.split(' ', 3)[1],
        'date': date,
        'up': up, 'down': down}
    d = pq(url=comments_url % id_)
    results = []
    if list(d) != [None]: # There are comments
        comments = [pq(x) for x in d('div.post')]
        for comment in comments:
            result = {'content': comment('p.texte').text(),
                    'author': comment('b').text(),
                    'replies': []}
            if comment.hasClass('reply'): # It's a reply
                results[-1]['replies'].append(result)
            else:
                results.append(result)
    return {'quote': quote, 'comments': results}

def vdm_parse_list(url):
    list_ = vdmfml_parse_list('http://www.viedemerde.fr' + url)
    for quote in list_:
        try:
            newcontent = quote['content'].encode('latin1', errors='ignore')
            json.dumps(newcontent)
            quote['content'] = newcontent
        except UnicodeDecodeError:
            pass
    return list_

@cache_page(60)
@format
def vdm_latest(request, page=1):
    return {'quotes': vdm_parse_list('/?page=%i' % (page-1)),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@cache_page(60)
@format
def vdm_random(request):
    return {'quotes': vdm_parse_list('/aleatoire'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def vdm_top(request, type_='week'):
    if type_ == 'ever':
        quotes = vdm_parse_list('/tops/top/')
    else:
        types = {'day': 'jour', 'week': 'semaine', 'month': 'mois'}
        quotes = vdm_parse_list('/tops/top/%s' % types[type_])
    return {'quotes': quotes,
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def vdm_show(request, id_):
    result = vdmfml_show('https://www.viedemerde.fr/inclassable/%i',
            'https://www.viedemerde.fr/ajax/comments/display.php?type=articles&id=%i',
            id_)
    recursive_comment_encoder(result['comments'], 'iso-8859-1')
    return result


############

def fml_parse_list(url):
    return vdmfml_parse_list('http://www.fmylife.com' + url)

@cache_page(60)
@format
def fml_latest(request, page=1):
    return {'quotes': fml_parse_list('/?page=%i' % (page-1)),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@cache_page(60)
@format
def fml_random(request):
    return {'quotes': fml_parse_list('/random'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def fml_top(request, type_='week'):
    if type_ == 'ever':
        quotes =  fml_parse_list('/tops/top/')
    else:
        quotes = fml_parse_list('/tops/top/%s' % type_)
    return {'quotes': quotes,
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def fml_show(request, id_):
    return vdmfml_show('https://www.fmylife.com/miscellaneous/%i',
            'https://www.fmylife.com/ajax/comments/display.php?type=articles&id=%i',
            id_)

############

def dtc_parse_list(url):
    d = pq(url='http://danstonchat.com' + url)
    messages = [pq(x) for x in d('div#content div.item')]
    results = []
    for message in messages:
        id_ = int(message('p.item-meta span.item-infos').attr('id'))
        content = message('p.item-content a').html() \
                .replace('<span class="decoration">', '') \
                .replace('</span>', '') \
                .strip() \
                .replace('<br />', '\n')
        up = int(message('p.item-meta a.voteplus').text().split(' ')[1])
        down = int(message('p.item-meta a.voteminus').text().split(' ')[1])
        results.append({'id': id_, 'content': entity2unicode(content),
            'up': up, 'down': down,
            'url': 'http://danstonchat.com/%i.html' % id_})
    return results

@cache_page(60)
@format
def dtc_latest(request, page='1'):
    page = int(page)
    return {'quotes': dtc_parse_list('/latest/%i.html' % page),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@cache_page(60)
@format
def dtc_random(request):
    return {'quotes': dtc_parse_list('/random.html'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def dtc_top(request):
    return {'quotes': dtc_parse_list('/top50.html'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def dtc_show(request, id_):
    id_ = int(id_)
    d = pq(url='http://danstonchat.com/%i.html' % id_)
    message = pq(d('div#content div.item'))
    id_ = int(message('p.item-meta span.item-infos').attr('id'))
    content = message('p.item-content a').html() \
            .replace('<span class="decoration">', '') \
            .replace('</span>', '') \
            .strip() \
            .replace('<br />', '\n')
    up = int(message('p.item-meta a.voteplus').text().split(' ')[1])
    down = int(message('p.item-meta a.voteminus').text().split(' ')[1])
    quote = {'id': id_, 'content': entity2unicode(content),
        'up': up, 'down': down}

    comments = [pq(x) for x in d('div#comments div.comment')]
    results = []
    for comment in comments:
        content = comment('div.comment-content p').text()
        author = comment('div.comment-content a').attr('href')[len('/geek/'):-len('.html')]
        results.append({'content': content, 'author': author, 'replies': []})
    return {'quote': quote, 'comments': results}


############

def pebkac_pq(url):
    opener = urllib2.build_opener()
    opener.addheaders = [('User-agent', 'OpenQuoteApi')]
    html = opener.open(url).read()
    return pq(html)

def pebkac_parse_list(url):
    d = pebkac_pq(url='http://www.pebkac.fr' + url)
    messages = [pq(x) for x in d('article')]
    results = []
    for message in messages:
        id_ = int(message('header a.permalink').text()[1:])
        content = message('p.content').html() \
                .replace('<br/>', '') \
                .split('<a', 1)[0] \
                .replace('&#13;', '') \
                .strip()
        note = int(message('div.score span').text())
        results.append({'id': id_, 'content': entity2unicode(content),
            'note': note, 'url': 'http://www.pebkac.fr/pebkac/%i/' % id_})
    print repr(results)
    return results

@cache_page(60 * 60)
@format
def pebkac_latest(request, page='1'):
    page = int(page)
    return {'quotes': pebkac_parse_list('/index.php?page=%i' % page),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@cache_page(60) # Caching a "random" page one hour does not make sense.
@format
def pebkac_random(request):
    return {'quotes': pebkac_parse_list('/pebkac-aleatoires.html'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60 * 60)
@format
def pebkac_top(request):
    return {'quotes': pebkac_parse_list('/index.php?p=top'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60 * 60)
@format
def pebkac_show(request, id_):
    id_ = int(id_)
    d = pebkac_pq(url='http://www.pebkac.fr/pebkac-%i.html' % id_)
    message = pq(d('article.pebkac'))
    content = message('p.content').html() \
            .replace('<br/>', '') \
            .split('<a', 1)[0] \
            .replace('&#13;', '') \
            .strip()
    author = message('header span.author').text()
    note = int(message('header div.score span').text())

    comments = [pq(x) for x in d('section#comments article')]
    results = []
    last_comment = None # pebkac has nested comments.
    for comment in comments:
        com_content = comment('div.text').text()
        com_author = comment('header .author').text()
        com_date = comment('footer div.time time').text()[2:]
        result = {'content': com_content, 'author': com_author, 'replies': []}
        if 'reply' in comment.outerHtml().split('>', 1)[0]:
            last_comment['replies'].append(result)
        else:
            results.append(result)
        last_comment = result
    return {'quote': {'content': content, 'id': id_, 'note': note, 'author': author},
            'comments': results}




############

def bash_parse_list(url):
    d = pq(url='http://bash.org' + url)
    messages = zip([pq(x) for x in d('p.quote')], [pq(x) for x in d('p.qt')])
    results = []
    for metadata, content in messages:
        id_ = int(metadata('a').attr('href')[1:])
        content = content.html() \
                .replace('\n', '') \
                .replace('\r', '') \
                .replace('<br/>', '\n')
        note = int(metadata.text().split('(')[1].split(')')[0])
        results.append({'id': id_, 'content': unescape(content),
            'note': note, 'url': 'http://bash.org/?%i' % id_})
    return results

@cache_page(60)
@format
def bash_latest(request, page=None):
    if page:
        # Search > and order by number
        quotes = bash_parse_list('/?search=%%3E&sort=1&show=%i' % page)
    else:
        quotes = bash_parse_list('/?latest')
    return {'quotes': quotes,
            'state': {'page': page or 1, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@cache_page(60)
@format
def bash_random(request, great_only=False):
    return {'quotes': bash_parse_list('/?random' + ('1' if great_only else '')),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def bash_top(request):
    return {'quotes': bash_parse_list('/?top'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@cache_page(60)
@format
def bash_show(request, id_):
    id_ = int(id_)
    quote = bash_parse_list('/?%i' % id_)[0]
    return {'quote': quote, 'comments': []}

############

@cache_page(60)
@format
def xkcd_latest(request, page=None):
    if page is None:
        page = 1
    last = requests.get('http://xkcd.com/info.0.json').json['num']
    results = []
    found = [0]
    def load(id_):
        try:
            data = requests.get('http://xkcd.com/%i/info.0.json' % id_).json
            results.append({'id': data['num'], 'content': data['title'] + '\n\n' + data['alt'],
                'image': data['img'], 'url': 'https://xkcd.com/%i/' % data['num']})
        finally:
            found[0] += 1
    for i in xrange((page-1)*10, (page)*10):
        threading.Thread(target=load, args=(last-i,)).start()
    while found[0] != 10:
        time.sleep(0.1)
    return {'quotes': results,
            'state': {'page': page or 1, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@cache_page(60)
@format
def xkcd_show(request, id_):
    id_ = int(id_)
    data = requests.get('http://xkcd.com/%i/info.0.json' % id_).json
    return {'quote': {'id': id_, 'content': data['title'] + '\n\n' + data['alt'],
                      'image': data['img']},
            'comments': [], 'id': data['num']}
