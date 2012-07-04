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

unescape = HTMLParser.HTMLParser().unescape

############

SITES = {
        'dtc': 'Dans ton chat',
        'pebkac': 'Pebkac',
        'vdm': 'Vie de merde',
        'fml': 'Fuck my life',
        'bash': 'bash.org',
        }
FIELDS = ['site', 'mode', 'type', 'page']

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
        return {'status': 'error', 'message': 'No \'site\' attribute.'}
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

