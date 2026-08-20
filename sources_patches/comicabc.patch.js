    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    loadPopularCustom = async (page) => {
        let res = await Network.get(`${ZhhantComicabcSource.baseUrl}/comic/h-${page}.html`, ZhhantComicabcSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load popular comics, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll(".container .row a.comicpic_col6");
        let comics = elements.map(el => {
            let coverSrc = (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : '');
            if (coverSrc.startsWith("/")) {
                coverSrc = `${ZhhantComicabcSource.baseUrl}${coverSrc}`;
            }
            return new Comic({
                id: (el.attributes['href'] || ''),
                title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
                cover: coverSrc,
            });
        });
        let hasNextPage = doc.querySelector("div.pager a span.mdi-skip-next") !== null;
        doc.dispose();
        return {
            comics: comics,
            maxPage: hasNextPage ? page + 1 : page,
        };
    }

    loadLatestCustom = async (page) => {
        let res = await Network.get(`${ZhhantComicabcSource.baseUrl}/comic/u-${page}.html`, ZhhantComicabcSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load latest comics, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll(".container .row .cat2_list a");
        let comics = elements.map(el => {
            let coverSrc = (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : '');
            if (coverSrc.startsWith("/")) {
                coverSrc = `${ZhhantComicabcSource.baseUrl}${coverSrc}`;
            }
            return new Comic({
                id: (el.attributes['href'] || ''),
                title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
                cover: coverSrc,
            });
        });
        let hasNextPage = doc.querySelector("div.pager a span.mdi-skip-next") !== null;
        doc.dispose();
        return {
            comics: comics,
            maxPage: hasNextPage ? page + 1 : page,
        };
    }

    loadSearchCustom = async (keyword, options, page) => {
        let url = `${ZhhantComicabcSource.baseUrl}/member/search.aspx?key=${encodeURIComponent(keyword)}&page=${page}`;
        let res = await Network.get(url, ZhhantComicabcSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load search results, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll(".container a.comicpic_col6");
        let comics = elements.map(el => {
            let coverSrc = (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : '');
            if (coverSrc.startsWith("/")) {
                coverSrc = `${ZhhantComicabcSource.baseUrl}${coverSrc}`;
            }
            return new Comic({
                id: (el.attributes['href'] || ''),
                title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
                cover: coverSrc,
            });
        });
        let hasNextPage = doc.querySelector("div.pager a span.mdi-skip-next") !== null;
        doc.dispose();
        return {
            comics: comics,
            maxPage: hasNextPage ? page + 1 : page,
        };
    }

    parseDetailsCustom = (comicDetails, htmlDoc) => {
        let authorEl = htmlDoc.querySelector(".item_content_box .item-info-author");
        if (authorEl && authorEl.text) {
            let author = authorEl.text;
            if (author.includes("作者: ")) {
                author = author.substring(author.indexOf("作者: ") + 4).trim();
            } else if (author.includes("作者：")) {
                author = author.substring(author.indexOf("作者：") + 3).trim();
            } else if (author.includes("作者:")) {
                author = author.substring(author.indexOf("作者:") + 3).trim();
            }
            comicDetails.subtitle = author;
            comicDetails.subTitle = author;
        }

        let statusEl = htmlDoc.querySelector(".item_content_box .item-info-status");
        if (statusEl && statusEl.text) {
            let statusText = statusEl.text.trim();
            if (statusText === "連載中") {
                comicDetails.status = 1;
            } else if (statusText === "已完結") {
                comicDetails.status = 2;
            } else {
                comicDetails.status = 0;
            }
        }
        if (comicDetails.cover && comicDetails.cover.startsWith("/")) {
            comicDetails.cover = `${ZhhantComicabcSource.baseUrl}${comicDetails.cover}`;
        }
        return comicDetails;
    }

    loadChapters = async (comicUrl) => {
        return this.parseChaptersCustom(comicUrl);
    }

    parseChaptersCustom = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${ZhhantComicabcSource.baseUrl}${comicUrl}`;
        let res = await Network.get(url, ZhhantComicabcSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("#chapters a, .comic_chapters a");

        let chaptersList = [];

        for (let el of elements) {
            let name = el.text || "";
            name = name.replace(/<script[\s\S]*?<\/script>/gi, "")
                       .replace(/document\.[^;]+;?/gi, "")
                       .replace(/isnew\([^)]*\);?/gi, "")
                       .replace(/getElementById\([^)]*\)/gi, "")
                       .trim();
            let onclick = el.attributes["onclick"] || "";
            let chapterUrl = "";

            if (onclick.includes("cview")) {
                let params = onclick.split("cview('")[1].split("'")[0];
                let comicId = params.split("-")[0];
                let chapterId = el.attributes["ch"] || (params.includes("-") ? params.replace('.html','').split("-")[1] : "1");

                if (!comicId || !chapterId) continue;

                chapterUrl = `${ZhhantComicabcSource.baseUrl}/view/${comicId}.html?ch=${chapterId}`;
            } else {
                let href = el.attributes["href"] || "";
                if (href.startsWith("http")) {
                    chapterUrl = href;
                } else if (href) {
                    if (href.startsWith("/")) {
                        chapterUrl = `${ZhhantComicabcSource.baseUrl}${href}`;
                    } else {
                        chapterUrl = href;
                    }
                }
            }
            if (chapterUrl) {
                chaptersList.push({ id: chapterUrl, title: name });
            }
        }

        chaptersList.reverse();
        let chaptersObj = {};
        for (let ch of chaptersList) {
            chaptersObj[ch.id] = ch.title;
        }

        doc.dispose();
        return chaptersObj;
    }

    parseEpisodeImagesCustom = (html, url) => {
        let scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
        let scriptMatch;
        let script = "";
        while ((scriptMatch = scriptRegex.exec(html)) !== null) {
            if (scriptMatch[1].includes("var ch=request")) {
                script = scriptMatch[1];
                break;
            }
        }
        if (!script) {
            throw new Error("Cannot find Comicabc image-data script (var ch=request)");
        }

        let comicMatch = script.match(/\bvar\s+ti\s*=\s*(\d+)\s*;/);
        let loopMatch = script.match(/for\s*\(\s*var\s+i\s*=\s*0\s*;\s*i\s*<\s*(\d+)\s*;\s*i\+\+\s*\)\s*\{([\s\S]*?)\bps\s*=\s*([A-Za-z_$][\w$]*)\s*;\s*if\s*\(\s*([A-Za-z_$][\w$]*)\s*==\s*ch\s*&&\s*\(\s*part\s*==\s*(?:''|"")\s*\|\|\s*part\s*==\s*([A-Za-z_$][\w$]*)\s*\)\s*\)/);
        if (!comicMatch || !loopMatch) {
            throw new Error("Cannot find Comicabc chapter-table metadata");
        }

        let recordCount = parseInt(loopMatch[1], 10);
        let loopPrefix = loopMatch[2];
        let pageCountVariable = loopMatch[3];
        let chapterVariable = loopMatch[4];
        let partVariable = loopMatch[5];
        let comicId = comicMatch[1];

        let assignmentRegex = /\bvar\s+([A-Za-z_$][\w$]*)\s*=\s*lc\s*\(\s*([A-Za-z_$][\w$]*)\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*i\s*\*\s*\([^)]*\)\s*\+\s*(\d+)(?:\s*,\s*(\d+))?\s*\)\s*\)\s*;/g;
        let assignments = [];
        let assignmentMatch;
        let substringFunction = "";
        let tableVariable = "";
        while ((assignmentMatch = assignmentRegex.exec(loopPrefix)) !== null) {
            if ((substringFunction && substringFunction !== assignmentMatch[2]) ||
                (tableVariable && tableVariable !== assignmentMatch[3])) {
                throw new Error("Inconsistent Comicabc chapter-table access");
            }
            substringFunction = assignmentMatch[2];
            tableVariable = assignmentMatch[3];
            assignments.push({
                name: assignmentMatch[1],
                offset: parseInt(assignmentMatch[4], 10),
            });
        }

        let srcMatch = script.match(/\.src\s*=\s*(unescape\([\s\S]*?\))\s*;/);
        if (!srcMatch || assignments.length !== 5) {
            throw new Error("Cannot determine Comicabc chapter-record layout");
        }
        let serverMatch = srcMatch[1].match(/\b([A-Za-z_$][\w$]*)\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*0\s*,\s*1\s*\)/);
        let tokenMatch = srcMatch[1].match(/\b([A-Za-z_$][\w$]*)\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*mm\s*\(\s*pg\s*\)\s*,\s*3\s*\)/);
        if (!serverMatch || !tokenMatch ||
            serverMatch[1] !== substringFunction || tokenMatch[1] !== substringFunction) {
            throw new Error("Cannot determine Comicabc image URL fields");
        }
        let serverVariable = serverMatch[2];
        let tokenVariable = tokenMatch[2];

        let fieldFor = (name) => {
            for (let assignment of assignments) {
                if (assignment.name === name) return assignment;
            }
            return null;
        };
        let roleNames = [serverVariable, tokenVariable, chapterVariable, pageCountVariable, partVariable];
        for (let roleIndex = 0; roleIndex < roleNames.length; roleIndex++) {
            if (!fieldFor(roleNames[roleIndex]) || roleNames.indexOf(roleNames[roleIndex]) !== roleIndex) {
                throw new Error("Ambiguous Comicabc chapter-record layout");
            }
        }

        let serverField = fieldFor(serverVariable);
        let tokenField = fieldFor(tokenVariable);
        let chapterField = fieldFor(chapterVariable);
        let pageCountField = fieldFor(pageCountVariable);
        let partField = fieldFor(partVariable);
        let recordWidth = partField.offset + 1;

        let tableAssignmentRegex = /\bvar\s+([A-Za-z_$][\w$]*)\s*=\s*(['"])([\s\S]*?)\2\s*;/g;
        let tableAssignmentMatch;
        let table = "";
        while ((tableAssignmentMatch = tableAssignmentRegex.exec(script)) !== null) {
            if (tableAssignmentMatch[1] === tableVariable) {
                table = tableAssignmentMatch[3];
                break;
            }
        }
        if (!table || table.length < recordCount * recordWidth) {
            throw new Error("Cannot find complete Comicabc chapter table");
        }

        let chapterParamMatch = url.match(/[?&]ch=([^&#]*)/);
        let chapterAndPage = chapterParamMatch ? chapterParamMatch[1].split("-")[0] : "1";
        chapterAndPage = chapterAndPage || "1";
        let partMatch = chapterAndPage.match(/[a-z]$/);
        let requestedPart = partMatch ? partMatch[0] : "";
        let targetChapter = parseInt(requestedPart ? chapterAndPage.slice(0, -1) : chapterAndPage, 10);
        if (isNaN(targetChapter)) {
            throw new Error(`Invalid Comicabc chapter id: ${chapterAndPage}`);
        }

        let alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
        let decodeRecordValue = (value) => {
            if (value.length !== 2) return value;
            if (value[0] === "Z") return 8000 + alphabet.indexOf(value[1]);
            return alphabet.indexOf(value[0]) * 52 + alphabet.indexOf(value[1]);
        };

        let targetRecord = "";
        for (let recordIndex = 0; recordIndex < recordCount; recordIndex++) {
            let recordOffset = recordIndex * recordWidth;
            let recordChapter = decodeRecordValue(table.substring(recordOffset + chapterField.offset, recordOffset + chapterField.offset + 2));
            let recordPart = table.substring(recordOffset + partField.offset, recordOffset + partField.offset + 1);
            if (recordChapter === targetChapter && (!requestedPart || recordPart === requestedPart)) {
                targetRecord = table.substring(recordOffset, recordOffset + recordWidth);
                break;
            }
        }
        if (!targetRecord) {
            throw new Error(`Comicabc chapter record not found: ${chapterAndPage}`);
        }

        let nextTokenOffset = recordWidth;
        for (let assignment of assignments) {
            if (assignment.offset > tokenField.offset && assignment.offset < nextTokenOffset) {
                nextTokenOffset = assignment.offset;
            }
        }
        let serverAndPath = String(decodeRecordValue(targetRecord.substring(serverField.offset, serverField.offset + 2)));
        let pageTokens = targetRecord.substring(tokenField.offset, nextTokenOffset);
        let recordChapter = decodeRecordValue(targetRecord.substring(chapterField.offset, chapterField.offset + 2));
        let pageCount = decodeRecordValue(targetRecord.substring(pageCountField.offset, pageCountField.offset + 2));
        let recordPart = targetRecord.substring(partField.offset, partField.offset + 1);
        if (serverAndPath.length !== 2 || typeof pageCount !== "number" || pageTokens.length !== 40) {
            throw new Error("Malformed Comicabc target chapter record");
        }

        let chapterPath = `${recordChapter}${recordPart === "0" ? "" : recordPart}`;
        let images = [];
        for (let page = 1; page <= pageCount; page++) {
            let tokenOffset = (parseInt((page - 1) / 10) % 10) + (((page - 1) % 10) * 3);
            let pageNumber = page < 10 ? `00${page}` : page < 100 ? `0${page}` : String(page);
            images.push(`https://img${serverAndPath[0]}.8comic.com/${serverAndPath[1]}/${comicId}/${chapterPath}/${pageNumber}_${pageTokens.substring(tokenOffset, tokenOffset + 3)}.jpg`);
        }
        return images;
    }

    loadEpCustom = async (comicId, epId) => {
        let url = epId.startsWith("http") ? epId : `${ZhhantComicabcSource.baseUrl}${epId}`;
        let pageListHeaders = {
            ...ZhhantComicabcSource.headers,
            "Referer": comicId.startsWith("http") ? comicId : `${ZhhantComicabcSource.baseUrl}/`
        };
        let res = await Network.get(url, pageListHeaders);
        if (res.status !== 200) {
            throw new Error(`Failed to load episode, status: ${res.status}`);
        }
        return { images: this.parseEpisodeImagesCustom(res.body, url) };
    }

    onImageLoadCustom = (url, comicId, epId) => {
        return {
            url: url,
            headers: {
                ...ZhhantComicabcSource.headers,
                "Referer": "https://articles.onemoreplace.tw/",
            }
        };
    }
