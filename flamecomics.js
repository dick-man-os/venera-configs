/**
 * @file en_flamecomics.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.en.flamecomics
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.4.50
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class EnFlamecomicsSource extends ComicSource {
    name = "Flame Comics"
    key = "en_flamecomics"
    version = "1.0.0"
    minAppVersion = "1.6.0"

    static baseUrl = "https://flamecomics.xyz"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {

    }

    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                return await this.loadPopularCustom(page);
            }
        },
        {
            title: "Latest",
            type: "multiPageComicList",
            load: async (page) => {
                return await this.loadLatestCustom(page);
            }
        }
    ]

    // Search
    search = {
        load: async (keyword, options, page) => {
            return await this.loadSearchCustom(keyword, options, page);
        }
    }

    // Comic Details and Reader Loading
    comic = {
        loadInfo: async (id) => {
            let url = id.startsWith("http") ? id : `${EnFlamecomicsSource.baseUrl}${id}`;
            let res = await Network.get(url, EnFlamecomicsSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("h1.subj, h3.subj");
            let authorEl = doc.querySelector(".author") || doc.querySelector(".author_area");
            let descEl = doc.querySelector("#_asideDetail p.summary");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = (doc.querySelector('.detail_header .thmb img') ? (doc.querySelector('.detail_header .thmb img').attributes['src'] || '') : '');


            let chapters = await this.loadChapters(id);

            let comicDetails = new ComicDetails({
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                tags: {},
                chapters: chapters,
            });

            comicDetails = this.parseDetailsCustom(comicDetails, doc);
            doc.dispose();
            return comicDetails;
        },

        loadEp: async (comicId, epId) => {
            return await this.loadEpCustom(comicId, epId);
        },

        onImageLoad: (url, comicId, epId) => ({
            url: url,
            headers: {
                ...EnFlamecomicsSource.headers,
                "Referer": `${EnFlamecomicsSource.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...EnFlamecomicsSource.headers,
                "Referer": `${EnFlamecomicsSource.baseUrl}/`,
            },
        }),
    }

    _buildId = "";

    async getBuildId() {
        let res = await Network.get(EnFlamecomicsSource.baseUrl, EnFlamecomicsSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to fetch buildId, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let nextDataEl = doc.querySelector("script#__NEXT_DATA__");
        if (!nextDataEl) {
            doc.dispose();
            throw new Error("Failed to find __NEXT_DATA__");
        }
        let nextData = JSON.parse(nextDataEl.text);
        this._buildId = nextData.buildId;
        doc.dispose();
        return this._buildId;
    }

    async fetchNextApi(pathSegments, isRetry = false) {
        if (!this._buildId) {
            await this.getBuildId();
        }
        let path = `_next/data/${this._buildId}/${pathSegments}`;
        let url = `${EnFlamecomicsSource.baseUrl}/${path}`;

        let res = await Network.get(url, EnFlamecomicsSource.headers);

        if (res.status === 404 && !isRetry) {
            // refresh build id and retry exactly once
            await this.getBuildId();
            return await this.fetchNextApi(pathSegments, true);
        }

        if (res.status !== 200) {
            throw new Error(`Next.js API failed with status ${res.status}`);
        }
        return JSON.parse(res.body);
    }

    loadPopularCustom = async (page) => {
        let json = await this.fetchNextApi(`browse.json`);
        let series = json.pageProps.series.filter(s => s.series_id != null);
        series.sort((a, b) => (b.views || 0) - (a.views || 0));

        let itemsPerPage = 20;
        let startIndex = (page - 1) * itemsPerPage;
        let endIndex = Math.min(page * itemsPerPage, series.length);

        let paged = series.slice(startIndex, endIndex);

        let comics = paged.map(s => {
            let coverUrl = `https://cdn.flamecomics.xyz/uploads/images/series/${s.series_id}/${s.cover}?${s.last_edit}#thumbnail`;
            return new Comic({
                id: `/series/${s.series_id}`,
                title: s.title,
                cover: coverUrl
            });
        });

        return {
            comics: comics,
            maxPage: endIndex < series.length ? page + 1 : page
        };
    }

    loadLatestCustom = async (page) => {
        let json = await this.fetchNextApi(`index.json`);
        let series = json.pageProps.latestEntries.blocks[0].series;

        let comics = series.map(s => {
            let coverUrl = `https://cdn.flamecomics.xyz/uploads/images/series/${s.series_id}/${s.cover}?${s.last_edit}#thumbnail`;
            return new Comic({
                id: `/series/${s.series_id}`,
                title: s.title,
                cover: coverUrl
            });
        });

        return {
            comics: comics,
            maxPage: 1
        };
    }

    loadSearchCustom = async (keyword, options, page) => {
        let json = await this.fetchNextApi(`browse.json`);
        let series = json.pageProps.series.filter(s => s.series_id != null);

        let query = keyword.toLowerCase().replace(/[^a-z0-9 ]/g, "");

        let filtered = series.filter(s => {
            let titles = [s.title];
            if (s.altTitles) titles = titles.concat(s.altTitles);

            return titles.some(t => {
                let cleanTitle = t.toLowerCase().replace(/[^a-z0-9 ]/g, "");
                return cleanTitle.includes(query);
            });
        });

        let itemsPerPage = 20;
        let startIndex = (page - 1) * itemsPerPage;
        let endIndex = Math.min(page * itemsPerPage, filtered.length);

        let paged = filtered.slice(startIndex, endIndex);

        let comics = paged.map(s => {
            let coverUrl = `https://cdn.flamecomics.xyz/uploads/images/series/${s.series_id}/${s.cover}?${s.last_edit}#thumbnail`;
            return new Comic({
                id: `/series/${s.series_id}`,
                title: s.title,
                cover: coverUrl
            });
        });

        return {
            comics: comics,
            maxPage: endIndex < filtered.length ? page + 1 : page
        };
    }

    _seriesDataCache = {};

    parseChaptersCustom = async (comicUrl) => {
        let parts = comicUrl.split('/').filter(p => p.length > 0);
        let seriesID = parts[parts.length - 1]; 

        let json = await this.fetchNextApi(`series/${seriesID}.json?id=${seriesID}`);

        // Cache the series data for Details
        this._seriesDataCache[seriesID] = json.pageProps.series;

        let chapters = json.pageProps.chapters.map(ch => {
            let chNumStr = ch.chapter.toString();
            if (chNumStr.endsWith(".0")) chNumStr = chNumStr.slice(0, -2);
            let name = `Chapter ${chNumStr}`;
            if (ch.title && ch.title.trim() !== "") {
                name += ` - ${ch.title}`;
            }
            return new Chapter({
                id: `/series/${ch.series_id}/${ch.token}`,
                title: name,
                url: `/series/${ch.series_id}/${ch.token}`
            });
        });

        return chapters;
    }

    parseDetailsCustom = (comicDetails, htmlDoc) => {
        // Extract seriesID from the HTML document's __NEXT_DATA__
        let nextDataEl = htmlDoc.querySelector("script#__NEXT_DATA__");
        if (!nextDataEl) return comicDetails;

        let nextData = JSON.parse(nextDataEl.text);
        let seriesID = nextData.query.id;
        if (!seriesID) return comicDetails;

        let seriesData = this._seriesDataCache[seriesID];
        if (seriesData) {
            comicDetails.title = seriesData.title || comicDetails.title;
            comicDetails.cover = `https://cdn.flamecomics.xyz/uploads/images/series/${seriesData.series_id}/${seriesData.cover}?${seriesData.last_edit}#thumbnail`;

            let desc = seriesData.description || "";
            desc = desc.replace(/<[^>]*>?/gm, ''); 

            let altNames = (seriesData.altTitles || []).map(a => a.trim()).filter(a => a.length > 0);
            if (altNames.length > 0) {
                if (desc) desc += "\n\n";
                desc += "Alternative Names:\n";
                altNames.forEach(name => { desc += `- ${name}\n`; });
            }
            comicDetails.description = desc;

            comicDetails.author = (seriesData.author || []).join(", ");
            comicDetails.artist = (seriesData.artist || []).join(", ");

            let tags = seriesData.tags || [];
            let allTags = [seriesData.type].concat(tags);
            comicDetails.tags = { "Genres": allTags };

            let s = (seriesData.status || "").toLowerCase();
            if (s === "ongoing") comicDetails.status = 1;
            else if (s === "completed") comicDetails.status = 2;
            else comicDetails.status = 0;

            comicDetails.subtitle = comicDetails.author;
            comicDetails.subTitle = comicDetails.author;
        }

        return comicDetails;
    }

    loadEpCustom = async (comicId, epId) => {
        let parts = epId.split('/').filter(p => p.length > 0);
        let seriesID = parts[1];
        let token = parts[2];

        let json = await this.fetchNextApi(`series/${seriesID}/${token}.json?id=${seriesID}&token=${token}`);
        let chapter = json.pageProps.chapter;

        let images = chapter.images.map(img => {
            return `https://cdn.flamecomics.xyz/uploads/images/series/${chapter.series_id}/${chapter.token}/${img.name}?${chapter.release_date}`;
        });

        return {
            images: images
        };
    }
}
