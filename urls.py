from django.conf.urls import patterns, include, url

from openquoteapi.api import *

urlpatterns = patterns('',
        url('^$', list_sites),

        url('^state/url/$', state_url),

        url('^vdm/quotes/latest/$', vdm_latest),
        url('^vdm/quotes/latest/(?P<page>[0-9]+)?/$', vdm_latest),
        url('^vdm/quotes/random/$', vdm_random),
        url('^vdm/quotes/top/$', vdm_top),
        url('^vdm/quotes/top/(?P<type>(day|week|month|ever))/$', vdm_top),
        url('^vdm/quotes/show/(?P<id_>[0-9]+)/', vdm_show),

        url('^fml/quotes/latest/$', fml_latest),
        url('^fml/quotes/latest/(?P<page>[0-9]+)?/$', fml_latest),
        url('^fml/quotes/random/$', fml_random),
        url('^fml/quotes/top/(?P<type>(day|week|month|ever))/$', fml_top),
        url('^fml/quotes/show/(?P<id_>[0-9]+)/', fml_show),

        url('^dtc/quotes/latest/$', dtc_latest),
        url('^dtc/quotes/latest/(?P<page>[0-9]+)?/$', dtc_latest),
        url('^dtc/quotes/random/$', dtc_random),
        url('^dtc/quotes/top/$', dtc_top),
        url('^dtc/quotes/show/(?P<id_>[0-9]+)/', dtc_show),

        url('^pebkac/quotes/latest/$', pebkac_latest),
        url('^pebkac/quotes/latest/(?P<page>[0-9]+)?/$', pebkac_latest),
        url('^pebkac/quotes/random/$', pebkac_random),
        url('^pebkac/quotes/top/$', pebkac_top),
        url('^pebkac/quotes/show/(?P<id_>[0-9]+)/', pebkac_show),

        url('^bash/quotes/latest/$', bash_latest),
        url('^bash/quotes/latest/(?P<page>[0-9]+)?/$', bash_latest),
        url('^bash/quotes/random/$', bash_random),
        url('^bash/quotes/random/great/$', bash_random, {'great_only': True}),
        url('^bash/quotes/top/$', bash_top),
        url('^bash/quotes/show/(?P<id_>[0-9]+)/', bash_show),

        url('^xkcd/quotes/latest/$', xkcd_latest),
        url('^xkcd/quotes/latest/(?P<page>[0-9]+)?/$', xkcd_latest),
        url('^xkcd/quotes/show/(?P<id_>[0-9]+)/', xkcd_show),
        )
