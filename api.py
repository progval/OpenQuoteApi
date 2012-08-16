import time
import PIL
import requests
import threading
import HTMLParser
from django.http import HttpResponse
from htmlentitydefs import entitydefs
import json

from pyquery import PyQuery as pq

def format(f):
    def newf(*args, **kwargs):
        if 'page' in kwargs:
            kwargs['page'] = int(kwargs['page'])
        return HttpResponse(json.dumps(f(*args, **kwargs)), mimetype='application/json')
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
        if 'type' not in state or state['type'] is None:
            state['type'] = 'week' if state['site'] == 'fml' else 'semaine'
        if state['type'] not in ('ever', 'toujours'):
            url += '%s/' % state['type']

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
        id_ = int(message('div.date div.left_part a').text()[1:])
        content = ''.join([x.text for x in message('a.fmllink')])
        up = int(message('div.date div.right_part span.dyn-vote-j-data').text())
        down = int(message('div.date div.right_part span span.dyn-vote-t-data').text())
        results.append({'id': id_, 'content': entity2unicode(content),
            'up': up, 'down': down})
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
    comments = [pq(x) for x in d('div.post')]
    results = []
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
        quote['content'] = quote['content'].encode('iso-8859-1')
    return list_

@format
def vdm_latest(request, page=1):
    return {'quotes': vdm_parse_list('/?page=%i' % page),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@format
def vdm_random(request):
    return {'quotes': vdm_parse_list('/aleatoire'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def vdm_top(request, type_='semaine'):
    if type_ == 'ever':
        quotes = vdm_parse_list('/tops/top/')
    else:
        types = {'day': 'jour', 'week': 'semaine', 'month': 'mois'}
        quotes = vdm_parse_list('/tops/top/%s' % types[type_])
    return {'quotes': quotes,
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

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

@format
def fml_latest(request, page=1):
    return {'quotes': fml_parse_list('/?page=%i' % page),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@format
def fml_random(request):
    return {'quotes': fml_parse_list('/random'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def fml_top(request, type_='week'):
    if type_ == 'ever':
        quotes =  fml_parse_list('/tops/top/')
    else:
        quotes = fml_parse_list('/tops/top/%s' % type_)
    return {'quotes': quotes,
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

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
            'up': up, 'down': down})
    return results

@format
def dtc_latest(request, page='1'):
    return {'quotes': dtc_parse_list('/latest/%i.html' % page),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@format
def dtc_random(request):
    return {'quotes': dtc_parse_list('/random.html'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def dtc_top(request):
    return {'quotes': dtc_parse_list('/top50.html'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def dtc_show(request, id_):
    id_ = int(id_)
    quote = dtc_parse_list('/%i.html' % id_)[0]
    return {'quote': quote, 'comments': []}


############

def pebkac_parse_list(url):
    d = pq(url='http://www.pebkac.fr' + url)
    messages = [pq(x) for x in d('table.pebkacMiddle')]
    results = []
    for message in messages:
        id_ = int(message('td.pebkacContent a.permalink').attr('href')[len('./pebkac-'):-len('.html')])
        content = message('td.pebkacContent').html() \
                .replace('<br />', '') \
                .split('<a', 1)[0] \
                .replace('&#13;', '') \
                .strip()
        note = int(message('td.pebkacLeft span').text())
        results.append({'id': id_, 'content': entity2unicode(content),
            'note': note})
    return results

@format
def pebkac_latest(request, page='1'):
    return {'quotes': pebkac_parse_list('/index.php?page=%i' % page),
            'state': {'page': page, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@format
def pebkac_random(request):
    return {'quotes': pebkac_parse_list('/pebkac-aleatoires.html'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def pebkac_top(request):
    return {'quotes': pebkac_parse_list('/index.php?p=top'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def pebkac_show(request, id_):
    id_ = int(id_)
    d = pq(url='http://www.pebkac.fr/pebkac-%i.html' % id_)
    message = pq(d('td#tdContenu table.pebkacMiddle'))
    content = message('td.pebkacContent').html() \
            .replace('<br />', '') \
            .split('<a', 1)[0] \
            .replace('&#13;', '') \
            .strip()
    author = message('td.pebkacContent span.pebkacIdentifiant').text()
    note = int(message('td.pebkacLeft span').text())

    comments = [pq(x) for x in d('table.commentTable')]
    results = []
    for comment in comments:
        content = comment('td.comContenu').text()
        author = comment('td.infoCom2 span.comPosteur').text()
        date = comment('td.infoCom2 span.comInfo').text()[2:]
        results.append({'content': content, 'author': author, 'replies': []})
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
            'note': note})
    return results

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

@format
def bash_random(request, great_only=False):
    return {'quotes': bash_parse_list('/?random' + ('1' if great_only else '')),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def bash_top(request):
    return {'quotes': bash_parse_list('/?top'),
            'state': {'page': 1, 'previous': False, 'next': False,
                      'gotopage': False}}

@format
def bash_show(request, id_):
    id_ = int(id_)
    quote = bash_parse_list('/?%i' % id_)[0]
    return {'quote': quote, 'comments': []}

############

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
                'image': data['img']})
        finally:
            found[0] += 1
    for i in xrange((page-1)*10, (page)*10):
        threading.Thread(target=load, args=(last-i,)).start()
    while found[0] != 10:
        time.sleep(0.1)
    return {'quotes': results,
            'state': {'page': page or 1, 'previous': (page != 1), 'next': True,
                      'gotopage': True}}

@format
def xkcd_show(request, id_):
    id_ = int(id_)
    data = requests.get('http://xkcd.com/%i/info.0.json' % id_).json
    return {'quote': {'id': id_, 'content': data['title'] + '\n\n' + data['alt'],
                      'image': data['img']},
            'comments': [], 'id': data['num']}
