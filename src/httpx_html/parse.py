import asyncio
from urllib.parse import urlparse, urlunparse, urljoin
from concurrent.futures._base import TimeoutError
from typing import Set, Union, List, MutableMapping, Optional, NewType, TYPE_CHECKING

import http.cookiejar
from pyquery import PyQuery

from lxml.html.clean import Cleaner
import lxml
from lxml import etree
from lxml.html import HtmlElement
from lxml.html import tostring as lxml_html_tostring
from lxml.html.soupparser import fromstring as soup_parse
from parse import search as parse_search
from parse import findall, Result
from w3lib.encoding import html_to_unicode

if TYPE_CHECKING:
    from .session import BaseSession

    _Attrs = MutableMapping
    _Containing = Union[str, List[str]]
    _CookieRender = MutableMapping[str, http.cookiejar.CookieJar]
    _Encoding = NewType('_Encoding', str)
    _Find = Union[List['Element'], 'Element']
    _Html = Union[str, bytes]
    _Links = Set[str]
    _Next = Union['HTML', List[str]]
    _NextSymbol = List[str]
    _Result = Union[List['Result'], 'Result']
    _Text = NewType('_Text', str)
    _Url = NewType('_Url', str)
    _XPath = Union[List[str], List['Element'], str, 'Element']

DEFAULT_ENCODING = 'utf-8'
DEFAULT_URL = 'https://example.org/'
DEFAULT_NEXT_SYMBOL = ['next', 'more', 'older']

cleaner = Cleaner()
cleaner.javascript = True
cleaner.style = True


class MaxRetries(Exception):

    def __init__(self, message):
        self.message = message


class BaseParser:
    '''A basic HTML/Element Parser, for Humans.

    :param element: The element from which to base the parsing upon.
    :param default_encoding: Which encoding to default to.
    :param html: HTML from which to base the parsing upon (optional).
    :param url: The URL from which the HTML originated, used for ``absolute_links``.
    '''

    __slots__ = ('element', 'url', 'skip_anchors', 'default_encoding',
                 '_encoding', '_html', '_lxml', '_pq')

    def __init__(
        self,
        *, element,
        default_encoding: Optional[str] = None,
        html:             '_Html' = None,
        url:              '_Url',
    ) -> None:
        self.element = element
        self.url = url
        self.skip_anchors = True
        self.default_encoding = default_encoding
        self._encoding = None
        self._html = html.encode(DEFAULT_ENCODING) if isinstance(html, str) else html
        self._lxml = None
        self._pq = None

    @property
    def raw_html(self) -> bytes:
        '''Bytes representation of the HTML content.
        '''
        if self._html:
            return self._html
        else:
            return etree.tostring(self.element, encoding='unicode').strip().encode(self.encoding)

    @raw_html.setter
    def raw_html(self, html: bytes) -> None:
        self._html = html

    @property
    def html(self) -> str:
        '''Unicode representation of the HTML content
        '''
        if self._html:
            return self.raw_html.decode(self.encoding, errors='replace')
        else:
            return etree.tostring(self.element, encoding='unicode').strip()

    @html.setter
    def html(self, html: str) -> None:
        self._html = html.encode(self.encoding)

    @property
    def encoding(self) -> '_Encoding':
        '''The encoding string to be used, extracted from the HTML and
        :class:`HTMLResponse <HTMLResponse>` headers.
        '''
        # scan meta tags for charset
        if not self._encoding and self._html:
            self._encoding = html_to_unicode(self.default_encoding, self._html)[0]
            # fall back to httpx's detected encoding if decode fails
            try:
                self.raw_html.decode(self.encoding, errors='replace')
            except UnicodeDecodeError:
                self._encoding = self.default_encoding

        return self._encoding if self._encoding else self.default_encoding

    @encoding.setter
    def encoding(self, enc: str) -> None:
        self._encoding = enc

    @property
    def pq(self) -> PyQuery:
        '''`PyQuery <https://github.com/gawel/pyquery/>`_ representation
        of the :class:`Element <Element>` or :class:`HTML <HTML>`.
        '''
        if self._pq is None:
            self._pq = PyQuery(self.lxml)

        return self._pq

    @property
    def lxml(self) -> HtmlElement:
        '''`lxml <https://lxml.de>`_ representation of the
        :class:`Element <Element>` or :class:`HTML <HTML>`.
        '''
        if self._lxml is None:
            try:
                self._lxml = soup_parse(self.html, features='html.parser')
            except ValueError:
                self._lxml = lxml.html.fromstring(self.raw_html)

        return self._lxml

    @property
    def text(self) -> '_Text':
        '''The text content of the :class:`Element <Element>` or :class:`HTML <HTML>`.
        '''
        return self.pq.text()

    @property
    def full_text(self) -> '_Text':
        '''The full text content (including links) of the :class:`Element <Element>`
        or :class:`HTML <HTML>`.
        '''
        return self.lxml.text_content()

    def find(
        self,
        selector:      str = "*",
        *, containing: '_Containing' = None,
        clean:         bool = False,
        first:         bool = False,
        _encoding:     str = None
    ) -> '_Find':
        '''Given a CSS Selector, returns a list of :class:`Element <Element>`
        objects or a single one.

        :param selector: CSS Selector to use.
        :param clean: Whether or not to sanitize the found HTML of ``<script>`` and
            ``<style>`` tags.
        :param containing: If specified, only return elements that contain the provided text.
        :param first: Whether or not to return just the first result.
        :param _encoding: The encoding format.

        Example CSS Selectors:

        - ``a``
        - ``a.someClass``
        - ``a#someID``
        - ``a[target=_blank]``

        See W3School's `CSS Selectors Reference
        <https://www.w3schools.com/cssref/css_selectors.asp>`_
        for more details.

        If ``first`` is ``True``, only returns the first :class:`Element <Element>` found.
        '''

        # Convert a single containing into a list.
        if isinstance(containing, str):
            containing = [containing]

        encoding = _encoding or self.encoding
        elements = [
            Element(element=found, url=self.url, default_encoding=encoding)
            for found in self.pq(selector)
        ]

        if containing:
            # elements_copy = elements.copy()
            # elements = []

            # for element in elements_copy:
            #     if any([c.lower() in element.full_text.lower() for c in containing]):
            #         elements.append(element)
            elements = [
                e for e in elements if any(c.lower() in e.full_text.lower() for c in containing)
            ]
            elements.reverse()

        # Sanitize the found HTML.
        if clean:
            elements_copy = elements.copy()
            elements = []

            for element in elements_copy:
                element.raw_html = lxml_html_tostring(cleaner.clean_html(element.lxml))
                elements.append(element)

        return _get_first_or_list(elements, first)

    def xpath(
        self,
        selector:  str,
        *, clean:  bool = False,
        first:     bool = False,
        _encoding: Optional[str] = None,
    ) -> '_XPath':
        '''Given an XPath selector, returns a list of :class:`Element <Element>` objects
        or a single one.

        :param selector: XPath Selector to use.
        :param clean: Whether or not to sanitize the found HTML of ``<script>`` and
            ``<style>`` tags.
        :param first: Whether or not to return just the first result.
        :param _encoding: The encoding format.

        If a sub-selector is specified (e.g. ``//a/@href``), a simple list of results is
        returned.

        See W3School's `XPath Examples
        <https://www.w3schools.com/xml/xpath_examples.asp>`_
        for more details.

        If ``first`` is ``True``, only returns the first :class:`Element <Element>` found.
        '''
        selected = self.lxml.xpath(selector)

        elements = [
            Element(element=selection, url=self.url, default_encoding=_encoding or self.encoding)
            if not isinstance(selection, etree._ElementUnicodeResult) else str(selection)
            for selection in selected
        ]  # type: List[Element]

        # Sanitize the found HTML
        if clean:
            elements_copy = elements.copy()
            elements = []

            for element in elements_copy:
                element.raw_html = lxml_html_tostring(cleaner.clean_html(element.lxml))
                elements.append(element)

        return _get_first_or_list(elements, first)

    def search(self, template: str) -> Result:
        '''Search the :class:`Element <Element>` for the given Parse template.

        :param template: The Parse template to use.
        '''

        return parse_search(template, self.html)

    def search_all(self, template: str) -> '_Result':
        '''Search the :class:`Element <Element>` (multiple times) for the given parse
        template.

        :param template: The Parse template to use.
        '''
        return [r for r in findall(template, self.html)]

    @property
    def links(self) -> '_Links':
        '''All found links on page, in as–is form.
        '''
        def gen():
            for link in self.find('a'):

                try:
                    href = link.attrs['href'].strip()
                    if (href and not (href.startswith('#') and self.skip_anchors)
                            and not href.startswith(('javascript:', 'mailto:'))):
                        yield href
                except KeyError:
                    pass

        return set(gen())

    def _make_absolute(self, link):
        '''Makes a given link absolute.
        '''
        # Parse the link with stdlib.
        parsed = urlparse(link)._asdict()

        # If link is relative, then join it with base_url.
        if not parsed['netloc']:
            return urljoin(self.base_url, link)

        # Link is absolute; if it lacks a scheme, add one from base_url.
        if not parsed['scheme']:
            parsed['scheme'] = urlparse(self.base_url).scheme

            # Reconstruct the URL to incorporate the new scheme.
            parsed = (v for v in parsed.values())
            return urlunparse(parsed)

        # Link is absolute and complete with scheme; nothing to be done here.
        return link

    @property
    def absolute_links(self) -> '_Links':
        '''All found links on page, in absolute form
        (`learn more <https://www.navegabem.com/absolute-or-relative-links.html>`_).
        '''
        def gen():
            for link in self.links:
                yield self._make_absolute(link)

        return set(gen())

    @property
    def base_url(self) -> '_Url':
        '''The base URL for the page. Supports the ``<base>`` tag
        (`learn more <https://www.w3schools.com/tags/tag_base.asp>`_).'''

        # support for <base> tag
        base = self.find('base', first=True)
        if base:
            result = base.attrs.get('href', '').strip()
            if result:
                return result

        # parse the url to separate out the path
        parsed = urlparse(self.url)._asdict()

        # remove any part of the path after the last '/'
        parsed['path'] = '/'.join(parsed['path'].split('/')[:-1]) + '/'

        # reconstruct the url with the modified path
        parsed = (v for v in parsed.values())
        url = urlunparse(parsed)

        return url


class Element(BaseParser):
    '''An element of HTML.

    :param element: The element from which to base the parsing upon.
    :param url: The URL from which the HTML originated, used for ``absolute_links``.
    :param default_encoding: Which encoding to default to.
    '''

    __slots__ = 'tag', 'lineno', '_attrs'  # , 'session'

    def __init__(
        self, *,
        element,
        url:              '_Url',
        default_encoding: Optional[str] = None,
    ) -> None:
        super().__init__(element=element, url=url, default_encoding=default_encoding)
        self.element = element
        self.tag = element.tag
        self.lineno = element.sourceline
        self._attrs = None

    def __repr__(self) -> str:
        attrs = [f'{a}={self.attrs[a]!r}' for a in self.attrs]
        return f'<Element {self.element.tag!r} {" ".join(attrs)}>'

    @property
    def attrs(self) -> '_Attrs':
        '''Returns a dictionary of the attributes of the :class:`Element <Element>`
        (`learn more <https://www.w3schools.com/tags/ref_attributes.asp>`_).
        '''
        if self._attrs is None:
            self._attrs = {k: v for k, v in self.element.items()}

            # split class and rel up, as there are usually many of them
            for attr in ['class', 'rel']:
                if attr in self._attrs:
                    self._attrs[attr] = tuple(self._attrs[attr].split())

        return self._attrs


class HTML(BaseParser):
    '''An HTML document, ready for parsing.

    :param url: The URL from which the HTML originated, used for ``absolute_links``.
    :param html: HTML from which to base the parsing upon (optional).
    :param default_encoding: Which encoding to default to.
    '''

    __slots__ = 'session', 'page', 'next_symbol'

    def __init__(
        self,
        *, session:       Optional['BaseSession'] = None,
        url:              str = DEFAULT_URL,
        html:             '_Html',
        default_encoding: Optional[str] = DEFAULT_ENCODING,
        async_:           bool = False,
    ) -> None:

        # convert incoming unicode HTML into bytes
        if isinstance(html, str):
            html = html.encode(DEFAULT_ENCODING)

        pq = PyQuery(html)
        super().__init__(
            element=pq('html') or pq.wrapAll('<html></html>')('html'),
            html=html,
            url=url,
            default_encoding=default_encoding
        )

        if session:
            self.session = session
        elif async_:
            from .session import AsyncHTMLSession
            self.session = AsyncHTMLSession()
        else:
            from .session import HTMLSession
            self.session = HTMLSession()

        self.page = None
        self.next_symbol = DEFAULT_NEXT_SYMBOL

    def __repr__(self) -> str:
        return f'<HTML url={self.url!r}>'

    def next(
        self,
        fetch:       bool = False,
        next_symbol: '_NextSymbol' = DEFAULT_NEXT_SYMBOL
    ) -> Optional['_Next']:
        '''Attempts to find the next page, if there is one. If ``fetch``
        is ``True`` (default), returns :class:`HTML <HTML>` object of
        next page. If ``fetch`` is ``False``, simply returns the next URL.
        '''

        def get_next():
            candidates = self.find('a', containing=next_symbol)

            for candidate in candidates:
                if candidate.attrs.get('href'):
                    # Support 'next' rel (e.g. reddit).
                    if 'next' in candidate.attrs.get('rel', []):
                        return candidate.attrs['href']

                    # Support 'next' in classnames.
                    for _class in candidate.attrs.get('class', []):
                        if 'next' in _class:
                            return candidate.attrs['href']

                    if 'page' in candidate.attrs['href']:
                        return candidate.attrs['href']

            try:
                # resort to the last candidate
                return candidates[-1].attrs['href']
            except IndexError:
                return None

        __next = get_next()

        if not __next:
            return None

        url = self._make_absolute(__next)

        if fetch:
            return self.session.get(url)
        else:
            return url

    def __iter__(self):

        next = self

        while True:
            yield next
            try:
                next = next.next(fetch=True, next_symbol=self.next_symbol).html
            except AttributeError:
                break

    def __next__(self):
        return self.next(fetch=True, next_symbol=self.next_symbol).html

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            url = self.next(fetch=False, next_symbol=self.next_symbol)
            if not url:
                break
            response = await self.session.get(url)
            return response.html

    def add_next_symbol(self, next_symbol):
        self.next_symbol.append(next_symbol)

    async def _async_render(
        self,
        *, url:     str,
        script:     str = None,
        scrolldown,
        sleep:      int,
        wait:       float,
        reload,
        content:    Optional[str],
        timeout:    Union[float, int],
        wait_until: Optional[Union[str, List[str]]],
        keep_page:  bool,
        cookies:    list = [{}],
    ):
        '''Handle page creation and js rendering. Internal use for render/arender methods.
        '''
        try:
            page = await self.browser.newPage()

            # wait before rendering the page, to prevent timeouts
            await asyncio.sleep(wait)

            if 'User-Agent' in self.session.headers:
                await page.setUserAgent(self.session.headers['User-Agent'])

            if cookies:
                for cookie in cookies:
                    if cookie:
                        await page.setCookie(cookie)

            options = {'timeout': int(timeout * 1000)}
            if wait_until is not None:
                options['waitUntil'] = wait_until

            # load the given page (GET request, obviously)
            if reload:
                await page.goto(url, options=options)
            else:
                await page.goto(f'data:text/html,{self.html}', options=options)

            result = None
            if script:
                result = await page.evaluate(script)

            if scrolldown:
                for _ in range(scrolldown):
                    await page._keyboard.down('PageDown')
                    await asyncio.sleep(sleep)
            else:
                await asyncio.sleep(sleep)

            if scrolldown:
                await page._keyboard.up('PageDown')

            # Return the content of the page, JavaScript evaluated.
            content = await page.content()
            if not keep_page:
                await page.close()
                page = None
            return content, result, page
        except TimeoutError:
            await page.close()
            page = None
            return None

    def _convert_cookiejar_to_render(
        self,
        session_cookiejar,
    ) -> '_CookieRender':
        '''
        Convert HTMLSession.cookies:cookiejar[] for browser.newPage().setCookie
        '''
        # |  setCookie(self, *cookies:dict) -> None
        # |      Set cookies.
        # |
        # |      ``cookies`` should be dictionaries which contain these fields:
        # |
        # |      * ``name`` (str): **required**
        # |      * ``value`` (str): **required**
        # |      * ``url`` (str)
        # |      * ``domain`` (str)
        # |      * ``path`` (str)
        # |      * ``expires`` (number): Unix time in seconds
        # |      * ``httpOnly`` (bool)
        # |      * ``secure`` (bool)
        # |      * ``sameSite`` (str): ``'Strict'`` or ``'Lax'``
        cookie_render = {}

        def __convert(cookiejar, key):
            try:
                v = eval(f'cookiejar.{key}')
                kv = '' if not v else {key: v}
            except Exception:
                kv = ''
            return kv

        keys = [
            'name',
            'value',
            'url',
            'domain',
            'path',
            'sameSite',
            'expires',
            'httpOnly',
            'secure',
        ]
        for key in keys:
            cookie_render.update(__convert(session_cookiejar, key))
        return cookie_render

    def _convert_cookiesjar_to_render(self) -> List['_CookieRender']:
        '''Convert ``HTMLSession.cookies`` for ``browser.newPage().setCookie``.
        '''
        if isinstance(self.session.cookies, http.cookiejar.CookieJar):
            return [self._convert_cookiejar_to_render(c) for c in self.session.cookies]

        return []

    def render(
        self,
        retries:              int = 8,
        script:               str = None,
        wait:                 float = 0.2,
        scrolldown:           bool = False,
        sleep:                int = 0,
        reload:               bool = True,
        timeout:              Union[float, int] = 8.0,
        wait_until:           Union[str, List[str]] = None,
        keep_page:            bool = False,
        cookies:              list = [{}],
        send_cookies_session: bool = False,
    ):
        '''Reloads the response in Chromium, and replaces HTML content
        with an updated version, with JavaScript executed.

        :param retries: The number of times to retry loading the page in Chromium.
        :param script: JavaScript to execute upon page load (optional).
        :param wait: The number of seconds to wait before loading the page, preventing
            timeouts (optional).
        :param scrolldown: Integer, if provided, of how many times to page down.
        :param sleep: Integer, if provided, of how many seconds to sleep after initial render.
        :param reload: If ``False``, content will not be loaded from the browser, but will be
            provided from memory.
        :param timeout: Timeout for rendering, in seconds.
        :param wait_until: When to consider the page loaded. Acceptable values are: ``load``
            (default) ``domcontentloaded``, ``networkidle0``, ``networkidle1``.
        :param keep_page: If ``True`` will allow you to interact with the browser page through
            ``r.html.page``.

        :param send_cookies_session: If ``True`` send ``HTMLSession.cookies`` convert.
        :param cookies: If not ``empty`` send ``cookies``.

        If ``scrolldown`` is specified, the page will scrolldown the specified
        number of times, after sleeping the specified amount of time
        (e.g. ``scrolldown=10, sleep=1``).

        If just ``sleep`` is provided, the rendering will wait *n* seconds, before
        returning.

        If ``script`` is specified, it will execute the provided JavaScript at
        runtime. Example:

        .. code-block:: python

            script = \"\"\"
                () => {
                    return {
                        width: document.documentElement.clientWidth,
                        height: document.documentElement.clientHeight,
                        deviceScaleFactor: window.devicePixelRatio,
                    }
                }
            \"\"\"

        Returns the return value of the executed  ``script``, if any is provided:

        .. code-block:: python

            >>> r.html.render(script=script)
            {'width': 800, 'height': 600, 'deviceScaleFactor': 1}

        Warning: the first time you run this method, it will download
        Chromium into your home directory (``~/.pyppeteer``).
        '''

        self.browser = self.session.browser  # Automatically create a event loop and browser
        content = None

        # automatically set reload to False, if example URL is being used
        if self.url == DEFAULT_URL:
            reload = False

        if send_cookies_session:
            cookies = self._convert_cookiesjar_to_render()

        for i in range(retries):
            if not content:
                try:

                    content, result, page = self.session.loop.run_until_complete(
                        self._async_render(
                            url=self.url, script=script, sleep=sleep, wait=wait, content=self.html,
                            reload=reload, scrolldown=scrolldown, timeout=timeout,
                            wait_until=wait_until, keep_page=keep_page, cookies=cookies)
                        )
                except TypeError:
                    pass
            else:
                break

        if not content:
            raise MaxRetries('Unable to render the page. Try increasing timeout.')

        html = HTML(url=self.url,
                    html=content.encode(DEFAULT_ENCODING),
                    default_encoding=DEFAULT_ENCODING)
        self.__dict__.update(html.__dict__)
        self.page = page
        return result

    async def arender(
        self,
        retries:              int = 8,
        script:               str = None,
        wait:                 float = 0.2,
        scrolldown:           bool = False,
        sleep:                int = 0,
        reload:               bool = True,
        timeout:              Union[float, int] = 8.0,
        wait_until:           Union[str, List[str]] = None,
        keep_page:            bool = False,
        cookies:              list = [{}],
        send_cookies_session: bool = False,
    ):
        '''Async version of render. Takes same parameters.
        '''

        self.browser = await self.session.browser
        content = None

        # automatically set Reload to False, if example URL is being used
        if self.url == DEFAULT_URL:
            reload = False

        if send_cookies_session:
            cookies = self._convert_cookiesjar_to_render()

        for _ in range(retries):
            if not content:
                try:

                    content, result, page = await self._async_render(
                        url=self.url, script=script, sleep=sleep, wait=wait, content=self.html,
                        reload=reload, scrolldown=scrolldown, timeout=timeout,
                        wait_until=wait_until, keep_page=keep_page, cookies=cookies
                    )
                except TypeError:
                    pass
            else:
                break

        if not content:
            raise MaxRetries('Unable to render the page. Try increasing timeout.')

        html = HTML(url=self.url,
                    html=content.encode(DEFAULT_ENCODING),
                    default_encoding=DEFAULT_ENCODING)
        self.__dict__.update(html.__dict__)
        self.page = page
        return result


def _get_first_or_list(lst, first=False):
    if first:
        try:
            return lst[0]
        except IndexError:
            return None
    else:
        return lst
