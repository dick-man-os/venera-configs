    // =========================================================================
    // Patched Implementation (Jujutsu Kaisen Page Logic)
    // =========================================================================

    loadChapters = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${EnReadjujutsukaisenmangaonlineSource.baseUrl}${comicUrl}`;
        let res = await Network.get(url, EnReadjujutsukaisenmangaonlineSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("div.w-full > div.bg-bg-secondary > div.grid");

        let chaptersList = elements.map(el => ({
            id: EnReadjujutsukaisenmangaonlineSource.resolveAbsoluteUrl((el.querySelector('.col-span-4 > a') ? (el.querySelector('.col-span-4 > a').attributes['href'] || '') : ''), url),
            title: (el.querySelector('.col-span-4 > a') ? el.querySelector('.col-span-4 > a').text : ''),
        }));

        let chaptersObj = {};
        for (let ch of chaptersList) {
            if (ch.id) {
                chaptersObj[ch.id] = ch.title || "";
            }
        }
        doc.dispose();

        // Hook for custom chapter parsing
        return this.parseChaptersCustom(chaptersObj, res.body);
    }

    /**
     * Placeholder hook for custom chapter transformations.
     */
    parseChaptersCustom = (chaptersObj, htmlBody) => {
        return chaptersObj;
    }

    /**
     * Custom page processing hook to handle placeholder data URIs and noscript duplicates.
     */
    parsePagesCustom = (images, htmlBody) => {
        let doc = new HtmlDocument(htmlBody);
        let container = doc.querySelector("div.js-pages-container");
        if (!container) {
            doc.dispose();
            return images; // fallback
        }

        let imgElements = container.querySelectorAll("img.js-page");
        let uniqueUrls = [];
        let seen = new Set();

        for (let el of imgElements) {
            let dataSrc = String(el.attributes['data-src'] || '').trim();
            let src = String(el.attributes['src'] || '').trim();
            let url = dataSrc || src;

            if (url) {
                url = EnReadjujutsukaisenmangaonlineSource.resolveAbsoluteUrl(url, EnReadjujutsukaisenmangaonlineSource.baseUrl);
                // The URL could be a data URI if not matched correctly, so skip those
                if (url.startsWith("data:")) continue;

                if (!seen.has(url)) {
                    seen.add(url);
                    uniqueUrls.push(url);
                }
            }
        }

        doc.dispose();

        if (uniqueUrls.length > 0) {
            return uniqueUrls;
        }
        return images;
    }
