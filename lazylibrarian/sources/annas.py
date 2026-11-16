#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software, you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

# Anna's Archive, direct provider

from lazylibrarian.sources.registry import DirectProvider, media_type, register_direct_provider


def search(book, search_type):
    from lazylibrarian.annas import anna_search
    return anna_search(book, media_type(search_type))


def on_error(provider, error):
    import lazylibrarian
    from lazylibrarian.annas import block_annas
    from lazylibrarian.blockhandler import BLOCKHANDLER
    from lazylibrarian.config2 import CONFIG
    dl_limit = CONFIG.get_int('ANNA_DLLIMIT')
    count = lazylibrarian.TIMERS['ANNA_REMAINING']
    if dl_limit and count <= 0:
        lazylibrarian.TIMERS['ANNA_REMAINING'] = 0
        block_annas(dl_limit)
    else:
        # use a short delay for site unavailable etc
        BLOCKHANDLER.block_provider(provider.name, error, delay=CONFIG.get_int('BLOCKLIST_TIMER'))


register_direct_provider(DirectProvider(key='ANNA', name='annas', label="Anna's Archive", search=search,
                                        on_error=on_error, result_title=True, telemetry='annas', order=30))
