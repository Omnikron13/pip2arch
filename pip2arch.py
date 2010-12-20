#!/usr/bin/python2
from __future__ import unicode_literals
from __future__ import with_statement

import sys
import xmlrpclib
import datetime
import logging
import argparse
import re

BLANK_PKGBUILD = """\
#Automatically generated by pip2arch on {date}

pkgname={pkg.outname}
pkgver={pkg.version}
pkgrel=1
pkgdesc="{pkg.description}"
url="{pkg.url}"
depends=('{pkg.pyversion}' {depends})
makedepends=({makedepends})
license=('{pkg.license}')
arch=('any')
source=('{pkg.download_url}')
md5sums=('{pkg.md5}')

build() {{
    cd $srcdir/{pkg.name}-{pkg.version}
    {pkg.pyversion} setup.py install --root="$pkgdir" --optimize=1
}}
"""

class pip2archException(Exception): pass
class VersionNotFound(pip2archException): pass
class LackOfInformation(pip2archException): pass

class Package(object):
    logging.info('Creating Server Proxy object')
    client = xmlrpclib.ServerProxy('http://pypi.python.org/pypi')
    depends = []
    makedepends = []
    data_received = False

    def get_package(self, name, outname, version=None):
        if version is None:
            versions = self.client.package_releases(name)
            if len(versions) > 1:
                version = self.choose_version(versions)
            else:
                logging.info('Using version %s' % versions[0])
                version = versions[0]
        self.version = version


        data = self.client.release_data(name, version)
        logging.info('Got release_data from PiPy')

        raw_urls = self.client.release_urls(name, version)
        logging.info('Got release_urls from PiPy')
        if not len(data):
            raise VersionNotFound('PyPi did not return any information for version {0}'.format(self.version))
        elif not len(raw_urls):
            if 'download_url' in data:
                download_url = data['download_url']
                if not 'tar.gz' in download_url:
                    raise LackOfInformation("Couln't find any tar.gz")
                else:
                    urls = {'url': download_url}
                    logging.warning('Got download link but no md5, you may have to search it by youself or generate it')
            else:
                raise LackOfInformation('PyPi did not return the necessary information to create the PKGBUILD')
        else:
            urls = {}
            for url in raw_urls:
                #if probabaly posix compat
                if url['filename'].endswith('.tar.gz'):
                    urls = url
            if not urls:
                raise pip2archException('Selected package version had no .tar.gz sources')
        logging.info('Parsed release_urls data')


        pyversion = urls.get('python_version', '')
        if pyversion in ('source', 'any'):
            self.pyversion = 'python2'
        if pyversion.startswith('3'):
            self.pyversion = 'python'
        else:
            self.pyversion = 'python2'
            logging.info('Falling back to default python version')
        logging.info('Parsed python_version')

        if outname is not None:
            self.outname = outname.lower()
        elif any(re.search(r'Librar(ies|y)', item) for item in data['classifiers']):
            #if this is a library
            self.outname = '{pyversion}-{pkgname}'.format(pyversion=self.pyversion, pkgname=name).lower()
            logging.info('Automaticly added {0} to the front of the package'.format(self.pyversion))
        else:
            self.outname = name.lower()

        try:
            self.name = data['name']
            self.description = data['summary']
            self.download_url = urls.get('url', '')
            self.md5 = urls.get('md5_digest', '')
            self.url = data.get('home_page', '')
            self.license = data['license']
        except KeyError:
            raise pip2archException('PiPy did not return needed information')
        logging.info('Parsed other data')
        self.data_received = True

    def search(self, term, interactive=False):
        results = self.client.search({'description': term[1:]})
        logging.info('Got search results for term {term} from PiPy server'.format(term=term))

        #If no results
        if not results:
            print 'No packages found'
            return

        for i, result in enumerate(results):
            i += 1
            print '{index}. {name} - {summary}'.format(index=i, name=result['name'], summary=result['summary'])

        #If we don't want talking, exit here
        if not interactive:
            #self.data_received = False
            return

        selection = raw_input('Enter the number of the PiPy package you would like to process\n')

        try:
            selection = int(selection.strip())
            selection -= 1
            chosen = results[selection]
        except (TypeError, IndexError):
            print 'Not a valid selection. Must be integer in range 1 - {length}'.format(length=len(results))
            retry = raw_input('Retry? [Y/n]\n')
            if retry.strip()[0] != 'n':
                #offer recurse on failure, maybe user will be smarter this time -.-
                return self.search(term)
            else:
                return

        name = chosen['name']
        outname = chosen['name']

        return self.get_package(name, outname)

    def choose_version(self, versions):
        print "Multiple versions found:"
        print ', '.join(versions)
        ver = raw_input('Which version would you like to use? ')
        if ver in versions:
            return ver
        else:
            print 'That was NOT one of the choices...'
            print 'Try again'
            return self.choose_version(versions)

    def add_depends(self, depends):
        self.depends += depends

    def add_makedepends(self, makedepends):
        self.makedepends += makedepends

    def render(self):
        depends = "'" + "' '".join(d for d in self.depends) + "'" if self.depends else ''
        makedepends = "'" + "' '".join(d for d in self.makedepends) + "'" if self.makedepends else ''
        return BLANK_PKGBUILD.format(pkg=self, date=datetime.date.today(), depends=depends, makedepends=makedepends)


def main():
    parser = argparse.ArgumentParser(description='Convert a PiPy package into an Arch Linux PKGBUILD.')
    parser.add_argument('pkgname', metavar='N', action='store',
                        help='Name of PyPi package for pip2arch to process')
    parser.add_argument('-v', '--version', dest='version', action='store',
                        help='The version of the speciied PyPi package to process')
    parser.add_argument('-o', '--output', dest='outfile', action='store',
                        default='PKGBUILD',
                        help='The file to output the generated PKGBUILD to')
    parser.add_argument('-s', '--search', dest='search', action='store_true',
                        help="Search for given package name, instead of building PKGBUILD")
    parser.add_argument('-i', '--interactive', dest='interactive', action='store_true',
                        help="Makes all commands interactive, prompting user for input.")
    parser.add_argument('-d', '--dependencies', dest='depends', action='append',
                        help="The name of a package that should be added to the depends array")
    parser.add_argument('-m', '--make-dependencies', dest='makedepends', action='append',
                        help="The name of a package that should be added to the makedepends array")
    parser.add_argument('-n', '--output-package-name', dest='outname', action='store', default=None,
                        help='The name of the package that pip2arch will generate')

    args = parser.parse_args()

    p = Package()

    if args.search:
        p.search(args.pkgname, interactive=args.interactive)
    else:
        p.get_package(name=args.pkgname, version=args.version, outname=args.outname)

    if args.depends:
        p.add_depends(args.depends)
    if args.makedepends:
        p.add_makedepends(args.makedepends)
    if p.data_received:
        print "Got package information"
        with open(args.outfile, 'w') as f:
            f.write(p.render())
        print "PKGBUILD written"

if __name__ == '__main__':
    try:
        main()
    except pip2archException as e:
        sys.exit('Pip2Arch error: {0}'.format(e))
    else:
        sys.exit(0)
