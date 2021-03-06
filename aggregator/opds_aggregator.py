#!/usr/bin/python2.5

#Copyright(c)2009 Internet Archive. Software license GPL version 3.

"""
Copyright(c)2009 Internet Archive. Software license AGPL version 3.

This file is part of bookserver.

    bookserver is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    bookserver is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with bookserver.  If not, see <http://www.gnu.org/licenses/>.
    
    The bookserver source is hosted at http://github.com/internetarchive/bookserver/

This script provides an OPDS frontend for the IA aggregator.
It works by translating data from solr queries in to OPDS-style atom feeds.
"""

import sys
sys.path.append("/petabox/sw/lib/python")

import cgi
import re
import urllib
import web
import string

import bookserver.catalog as catalog
import bookserver.catalog.output as output
import bookserver.device

numRows = 50

# You can customize pubInfo:
pubInfo = {
    'name'     : 'Open Library',
    'uri'      : 'http://www.archive.org',
    'opdsroot' : 'http://bookserver.archive.org/aggregator',
    'mimetype' : 'application/atom+xml;profile=opds',
    'solr_base': 'http://ia331527.us.archive.org:8983/solr/select/?version=2.2&wt=json',
    'url_base' : '/aggregator',
    'urnroot'  : 'urn:x-internet-archive:bookserver:aggregator',
}

urls = (
    '/(.*)/',                       'redirect',
    '/alpha.(xml|html)',            'alphaList',
    '/alpha/(.)(?:/(.*))?',         'alpha',
    '/provider/(\w+)(?:/(.*))?',    'provider',    
    '/providers.(xml|html)',        'providerList',
    
    # Searching
    '/opensearch.xml',              'openSearchDescription',
    '/opensearch(.*)',              'opensearch',
    '/search(.*)',                  'htmlsearch',

    '/'                 ,           'index',
    '/index\.(xml|html)',           'index',
    '/(.*)',                        'indexRedirect',         
)

types = {
    'xml'  : 'application/atom+xml;profile=opds',
    'html' : 'text/html',
}

providers = {
    'OReilly'   : "O'Reilly",
    'IA'        : "Internet Archive",
    'Feedbooks' : "Feedbooks",
}

application = web.application(urls, globals()).wsgifunc()


def getEnv(key, default = None):
    env = web.ctx['environ']
    if env.has_key(key):
        return env[key]
    else:
        return default
        
def getDevice():
    userAgent = getEnv('HTTP_USER_AGENT')
    if userAgent is not None:
        device = bookserver.device.Detect.createFromUserAgent(userAgent)
    else:
        device = None
    return device


# /
#______________________________________________________________________________
class index:
    def GET(self, mode='xml'):

        datestr = catalog.getCurrentDate()
        
        c = catalog.Catalog(
                            title     = pubInfo['name'] + ' Aggregator',
                            urn       = pubInfo['urnroot'],
                            url       = pubInfo['opdsroot'],
                            datestr   = datestr,
                            author    = pubInfo['name'],
                            authorUri = pubInfo['uri'],
                           )

            
        l = catalog.Link(url = 'alpha.'+mode, type = bookserver.catalog.Link.opds)
        e = catalog.Entry({'title'   : 'Alphabetical By Title',
                           'urn'     : pubInfo['urnroot'] + ':titles:all',
                           'updated' : datestr,
                           'content' : 'Alphabetical list of all titles.'
                         }, links=[l])
        c.addEntry(e)

        l = catalog.Link(url = 'providers.'+mode, type = bookserver.catalog.Link.opds)
        e = catalog.Entry({'title'   : 'By Provider',
                           'urn'     : pubInfo['urnroot'] + ':providers:all',
                           'updated' : datestr,
                           'content' : 'Listing of all publishers and sellers.'
                         }, links=[l])
        c.addEntry(e)

        #l = catalog.Link(url = 'devices.'+mode, type = types[mode])
        #e = catalog.Entry({'title'   : 'By Device',
        #                   'urn'     : pubInfo['urnroot'] + ':devices',
        #                   'updated' : datestr,
        #                   'content' : 'Filter by books compatible with your e-book reading device.'
        #                 }, links=[l])        
        #c.addEntry(e)
        
        osDescriptionDoc = 'http://bookserver.archive.org/aggregator/opensearch.xml'
        o = catalog.OpenSearch(osDescriptionDoc)
        c.addOpenSearch(o)
        
        if 'html' == mode:
            r = output.ArchiveCatalogToHtml(c, device = getDevice())
            web.header('Content-Type', 'text/html')
            return r.toString()
        else:        
            r = output.CatalogToAtom(c)
            web.header('Content-Type', pubInfo['mimetype'])
            return r.toString()

# /alpha/a/0
#______________________________________________________________________________
class alpha:

    def GET(self, letter, start):
        mode = 'xml'
        if not start:
            start = 0
        else:
            if start.endswith('.html'):
                start = start[:-5]
                mode = 'html'
            start = int(start)
           
            
        
        #TODO: add Image PDFs to this query
        solrUrl = pubInfo['solr_base'] + '&q=firstTitle%3A'+letter.upper()+'&sort=titleSorter+asc&rows='+str(numRows)+'&start='+str(start*numRows)
        titleFragment = 'books starting with "%s"' % (letter.upper())
        urn           = pubInfo['urnroot'] + ':%s:%d'%(letter, start)

        ingestor = catalog.ingest.SolrToCatalog(pubInfo, solrUrl, urn,
                                                start=start, numRows=numRows,
                                                urlBase='%s/alpha/%s/' % (pubInfo['url_base'], letter),
                                                titleFragment = titleFragment)
        c = ingestor.getCatalog()
    
        if 'html' == mode:
            web.header('Content-Type', 'text/html')
            r = output.ArchiveCatalogToHtml(c, device = getDevice())
            return r.toString()
        else:
            web.header('Content-Type', pubInfo['mimetype'])
            r = output.CatalogToAtom(c, fabricateContentElement=True)
            return r.toString()
            
# /alpha.xml
#______________________________________________________________________________
class alphaList:
    def alphaURL(self, extension, letter, start):
        url = 'alpha/%s/%d' % (letter, start)
        if 'xml' != extension:
            url += '.' + extension
        return url

    def GET(self, extension):
        #IA is continuously scanning books. Since this OPDS file is constructed
        #from search engine results, let's change the updated date every midnight
        #TODO: create a version of /alpha.xml with the correct updated dates,
        #and cache it for an hour to ease load on solr
        datestr = catalog.getCurrentDate()
                           
        c = catalog.Catalog(
                            title     = pubInfo['name'] + ' Aggregator - All Titles',
                            urn       = pubInfo['urnroot'] + ':titles:all',
                            url       = pubInfo['opdsroot'] + '/alpha.xml',
                            datestr   = datestr,
                            author    = pubInfo['name'],
                            authorUri = pubInfo['uri'],
                           )

        for letter in string.ascii_uppercase:
            lower = letter.lower()
                
            l = catalog.Link(url = self.alphaURL(extension, lower, 0), type = bookserver.catalog.Link.opds)        
            e = catalog.Entry({'title'   : 'Titles: ' + letter,
                               'urn'     : pubInfo['urnroot'] + ':titles:'+lower,
                               'updated' : datestr,
                               'content' : 'Titles starting with ' + letter
                             }, links=[l])
            c.addEntry(e)

        osDescriptionDoc = 'http://bookserver.archive.org/aggregator/opensearch.xml'
        o = catalog.OpenSearch(osDescriptionDoc)
        c.addOpenSearch(o)
        
        web.header('Content-Type', types[extension])

        if ('xml' == extension):
            r = output.CatalogToAtom(c)
        else:
            r = output.ArchiveCatalogToHtml(c, device = getDevice())

        return r.toString()

# /provider/x/0
#______________________________________________________________________________
class provider:
    def GET(self, domain, start):
        mode = 'xml'
        if not start:
            start = 0
        else:
            if start.endswith('.html'):
                start = start[:-5]
                mode = 'html'
            start = int(start)
        
        #TODO: add Image PDFs to this query
        solrUrl = pubInfo['solr_base'] + '&q=provider%3A'+domain+'&sort=titleSorter+asc&rows='+str(numRows)+'&start='+str(start*numRows)        
        titleFragment = 'books for provider ' + providers[domain]
        urn           = pubInfo['urnroot'] + ':provider:%s:%d' % (domain,start)

        ingestor = catalog.ingest.SolrToCatalog(pubInfo, solrUrl, urn,
                                                start=start, numRows=numRows,
                                                urlBase='%s/provider/%s/' % (pubInfo['url_base'], domain),
                                                titleFragment = titleFragment)
        c = ingestor.getCatalog()
    
        web.header('Content-Type', types[mode])

        if ('xml' == mode):
            r = output.CatalogToAtom(c, fabricateContentElement=True)
        else:
            r = output.ArchiveCatalogToHtml(c, device = getDevice(), provider = domain)

        return r.toString()


# /providers.xml
#______________________________________________________________________________
class providerList:
    def GET(self, mode):
        #TODO: get correct updated dates
        datestr = catalog.getCurrentDate()
                           
        c = catalog.Catalog(
                            title     = pubInfo['name'] + ' Aggregator - All Providers',
                            urn       = pubInfo['urnroot'] + ':providers:all',
                            url       = pubInfo['opdsroot'] + '/providers.' + mode,
                            datestr   = datestr,
                            author    = pubInfo['name'],
                            authorUri = pubInfo['uri'],
                           )
    
    
        for provider in providers:
            if 'html' == mode:
                ext = '.html' # $$$ should do URL mapping in output side?
            else:
                ext = ''
                
            l = catalog.Link(url = 'provider/'+provider+'/0'+ext, type = bookserver.catalog.Link.opds)
            e = catalog.Entry({'title'   : providers[provider],
                               'urn'     : pubInfo['urnroot'] + ':providers:'+provider, 
                               'updated' : datestr,
                               'content' : 'All Titles for provider ' + provider
                             }, links=[l])
            c.addEntry(e)

        osDescriptionDoc = 'http://bookserver.archive.org/aggregator/opensearch.xml'
        o = catalog.OpenSearch(osDescriptionDoc)
        c.addOpenSearch(o)
            
        web.header('Content-Type', types[mode])
        if ('xml' == mode):
            r = output.CatalogToAtom(c)
        else:
            r = output.ArchiveCatalogToHtml(c, device = getDevice())

        return r.toString()
        
# /opensearch
#______________________________________________________________________________        
class opensearch:
    def GET(self, query):
        params = cgi.parse_qs(web.ctx.query)

        if not 'start' in params:
            start = 0
        else:
            start = int(params['start'][0])

        q  = params['?q'][0]
        qq = urllib.quote(q)     
        solrUrl = pubInfo['solr_base'] + '&q=' + qq +'&sort=titleSorter+asc&rows='+str(numRows)+'&start='+str(start*numRows)
        
        # solrUrl       = pubInfo['solr_base'] + '&q='+qq+'+AND+mediatype%3Atexts+AND+(format%3A(LuraTech+PDF)+OR+scanner:google)&sort=month+desc&rows='+str(numRows)+'&start='+str(start*numRows)
        titleFragment = 'search results for ' + q
        urn           = pubInfo['urnroot'] + ':search:%s:%d' % (qq, start)

        ingestor = catalog.ingest.SolrToCatalog(pubInfo, solrUrl, urn,
                                                start=start, numRows=numRows,
                                                urlBase='%s/opensearch?q=%s&start=' % (pubInfo['url_base'], qq),
                                                titleFragment = titleFragment)

        c = ingestor.getCatalog()

        web.header('Content-Type', pubInfo['mimetype'])
        r = output.CatalogToAtom(c, fabricateContentElement=True)
        return r.toString()
        
# /search
#______________________________________________________________________________        
class htmlsearch:
    def GET(self, query):
        qs = web.ctx.query
        if qs.startswith('?'):
            qs = qs[1:]
        
        params = cgi.parse_qs(qs)

        if not 'start' in params:
            start = 0
        else:
            start = params['start'][0] # XXX hack for .html ending -- remove once fixed
            if start.endswith('.html'):
                start = start[:-5]
            start = int(start)

        if 'q' in params:
            q  = params['q'][0]
        else:
            q = ''
        
        # Provider-specific search              
        if 'provider' in params:
            providerMatch = re.search('(\w+)$', params['provider'][0])
            if providerMatch:
                provider = providerMatch.group(0)
                if not re.search('provider:', q):
                    if len(q) > 0:
                        q += ' AND '
                    q += 'provider:%s' % provider
            else:
                provider = None
        else:
            provider = None

        # Device-specific search
        # $$$ extend to other devices 
        if 'device' in params:
            deviceStr = params['device'][0]
            if re.search('Kindle', deviceStr):
                formatStr = 'format:mobi'
                if not re.search(formatStr, q): # XXX brittle
                    if len(q) > 0:
                        q += ' AND '
                    q += formatStr
        
        qq = urllib.quote(q)
        solrUrl = pubInfo['solr_base'] + '&q=' + qq +'&sort=titleSorter+asc&rows='+str(numRows)+'&start='+str(start*numRows)

        #solrUrl       = pubInfo['solr_base'] + '?q='+qq+'+AND+mediatype%3Atexts+AND+format%3A(LuraTech+PDF)&fl=identifier,title,creator,oai_updatedate,date,contributor,publisher,subject,language,format&rows='+str(numRows)+'&start='+str(start*numRows)+'&wt=json'        
        titleFragment = 'search results for ' + q
        urn           = pubInfo['urnroot'] + ':search:%s:%d' % (qq, start)

        ingestor = catalog.ingest.SolrToCatalog(pubInfo, solrUrl, urn,
                                                start=start, numRows=numRows,
                                                # XXX assuming calling from archive.org/bookserver/catalog
                                                # XXX HTML output is adding .html to end...
                                                urlBase='/bookserver/catalog/search?q=%s&start=' % (qq),
                                                titleFragment = titleFragment)

        c = ingestor.getCatalog()
        
        web.header('Content-Type', 'text/html')
        r = output.ArchiveCatalogToHtml(c, device = getDevice(), query = q, provider = provider)
        return r.toString()

# /opensearch.xml - Open Search Description
#______________________________________________________________________________        
class openSearchDescription:
    def GET(self):
        web.header('Content-Type', 'application/atom+xml')
        return """<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
    <ShortName>Open Library Catalog Search</ShortName>
    <Description>Search Open Library's BookServer Catalog</Description>
    <Url type="application/atom+xml" 
        template="%s/opensearch?q={searchTerms}&amp;start={startPage?}"/>
</OpenSearchDescription>""" % (pubInfo['opdsroot'])
        

# redirect to remove trailing slash
#______________________________________________________________________________        
class redirect:
    def GET(self, path):
        web.seeother('/' + path)           

# redirect to index
#______________________________________________________________________________        
class indexRedirect:
    def GET(self, path):
        if path.endswith('.html'):
            web.seeother('/index.html')
        else:
            web.seeother('/')


# main() - standalone mode
#______________________________________________________________________________        
if __name__ == "__main__":
    #run in standalone mode
    app = web.application(urls, globals())
    app.run()