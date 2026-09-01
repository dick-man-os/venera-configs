    // =========================================================================
    // Patched Implementation (Jujutsu Kaisen Page Logic)
    // =========================================================================

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
            let dataSrc = el.attributes['data-src'];
            let src = el.attributes['src'];
            let url = dataSrc ? dataSrc : src;

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
