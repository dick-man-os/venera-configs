    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    loadChapters = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${this.baseUrl}${comicUrl}`;
        let res = await Network.get(url, ZhhansManhuasheSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("#chapter-list > div.chapter-item > a");

        let chaptersList = elements.map(el => ({
            id: (el.attributes['href'] || ''),
            title: (el.text || ''),
        }));
        chaptersList.reverse();

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

    parseDetailsCustom = (comicDetails, htmlDoc) => {
        // Author extraction using :contains(作者：)
        let statsEls = htmlDoc.querySelectorAll("div.comic-stats > div.stat-item");
        for (let el of statsEls) {
            let text = el.text || "";
            if (text.includes("作者：")) {
                let author = text.replace("作者：", "").trim();
                comicDetails.subtitle = author;
                comicDetails.subTitle = author;
                break;
            }
        }

        // Status and Genre extraction
        let tagsEls = htmlDoc.querySelectorAll("div.comic-meta-info > div.comic-tags > span");
        if (tagsEls.length > 0) {
            let lastTag = tagsEls[tagsEls.length - 1].text.trim();
            if (lastTag === "连载" || lastTag === "连载中") {
                comicDetails.status = 1; // ONGOING
            } else if (lastTag === "完结" || lastTag === "已完结") {
                comicDetails.status = 2; // COMPLETED
            } else {
                comicDetails.status = 0; // UNKNOWN
            }

            let genres = [];
            for (let el of tagsEls) {
                if (el.text) {
                    genres.push(el.text.trim());
                }
            }
            if (genres.length > 0) {
                comicDetails.tags = comicDetails.tags || {};
                comicDetails.tags["Tags"] = genres;
            }
        }

        return comicDetails;
    }

    parseChaptersCustom = (chaptersObj, htmlBody) => {
        return chaptersObj;
    }

    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
