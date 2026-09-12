import copy
import json
import sys
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.patcher.js_patcher import patch_js
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.validator.validate_registry import (
    derive_index,
    is_bcp47_locale,
    validate_registry_data,
    validate_repository,
)


EXPECTED_RUNTIME_KEYS = {
    "bh3": "keiyoushi_5943234929466346733",
    "guazimanhua": "keiyoushi_9103931521355991619",
    "terrahistoricus": "keiyoushi_4585134706567717130",
    "baozi": "baozi",
    "ccc": "ccc",
    "comic_walker": "comic_walker",
    "comicabc": "zh_Hant_comicabc",
    "comick": "comick",
    "copy_manga": "copy_manga",
    "copy_manga_multi_accounts": "copy_manga",
    "dongmanmanhua_zh_hans": "keiyoushi_4222375517460530289",
    "ehentai": "ehentai",
    "flamecomics": "en_flamecomics",
    "globalcomix_zh_hans": "keiyoushi_7151191693036508367",
    "goda": "goda",
    "hanman18": "keiyoushi_5092568988625041973",
    "happy": "happy",
    "hcomic": "hcomic",
    "hitomi": "hitomi",
    "hot_manga": "hot_manga",
    "ikmmh": "ikmmh",
    "jcomic": "jcomic",
    "jm": "jm",
    "kavita": "kavita",
    "komga": "komga",
    "komiic": "Komiic",
    "lanraragi": "lanraragi",
    "manga_dex": "manga_dex",
    "mangadex_zh_hans": "keiyoushi_5148895169070562838",
    "mangadex_zh_hant": "keiyoushi_1493666528525752601",
    "manhuagui": "ManHuaGui",
    "manhuaren": "manhuaren",
    "manhuashe": "zh_Hans_manhuashe",
    "manhuawu": "keiyoushi_3279300917142951720",
    "manwaba": "manwaba",
    "mh1234": "mh1234",
    "mh18": "mh18",
    "mxs": "mxs",
    "mycomic": "mycomic",
    "namicomi_zh_hans": "keiyoushi_1163192659786040070",
    "namicomi_zh_hant": "keiyoushi_7859611418350123856",
    "nhentai": "nhentai",
    "picacg": "picacg",
    "readblackclovermangaonline": "en_readblackclovermangaonline",
    "readfairytailedenszeromangaonline": "en_readfairytailedenszeromangaonline",
    "readjujutsukaisenmangaonline": "en_readjujutsukaisenmangaonline",
    "readkingdommangaonline": "en_readkingdommangaonline",
    "readnanatsunotaizai7deadlysinsmangaonline": "en_readnanatsunotaizai7deadlysinsmangaonline",
    "readonepiecemangaonline": "en_readonepiecemangaonline",
    "readsololevelingmangamanhwaonline": "en_readsololevelingmangamanhwaonline",
    "readtokyoghoulretokyoghoulmangaonline": "en_readtokyoghoulretokyoghoulmangaonline",
    "shonen_jump_plus": "shonen_jump_plus",
    "webtoons": "en_webtoons",
    "webtoons_zh_hant": "zh_Hant_webtoons",
    "wnacg": "wnacg",
    "ykmh": "ykmh",
    "zaimanhua": "zaimanhua",
}

CONVERTED_ARTIFACTS = {
    "bh3",
    "guazimanhua",
    "terrahistoricus",
    "comicabc",
    "dongmanmanhua_zh_hans",
    "flamecomics",
    "globalcomix_zh_hans",
    "hanman18",
    "manhuawu",
    "manhuashe",
    "mangadex_zh_hans",
    "mangadex_zh_hant",
    "namicomi_zh_hans",
    "namicomi_zh_hant",
    "webtoons",
    "webtoons_zh_hant",
    "readblackclovermangaonline",
    "readfairytailedenszeromangaonline",
    "readjujutsukaisenmangaonline",
    "readkingdommangaonline",
    "readnanatsunotaizai7deadlysinsmangaonline",
    "readonepiecemangaonline",
    "readsololevelingmangamanhwaonline",
    "readtokyoghoulretokyoghoulmangaonline",
}

EXPECTED_CONVERTED_UPSTREAM = {
    "bh3": ("5943234929466346733", "1.4.4", "1.4"),
    "guazimanhua": ("9103931521355991619", "1.6.6", "1.6"),
    "terrahistoricus": ("4585134706567717130", "1.4.4", "1.4"),
    "mangadex_zh_hans": ("5148895169070562838", "1.4.212", "1.4"),
    "mangadex_zh_hant": ("1493666528525752601", "1.4.212", "1.4"),
    "dongmanmanhua_zh_hans": ("4222375517460530289", "1.4.6", "1.4"),
    "globalcomix_zh_hans": ("7151191693036508367", "1.4.4", "1.4"),
    "hanman18": ("5092568988625041973", "1.4.3", "1.4"),
    "manhuawu": ("3279300917142951720", "1.4.9", "1.4"),
    "namicomi_zh_hans": ("1163192659786040070", "1.4.6", "1.4"),
    "namicomi_zh_hant": ("7859611418350123856", "1.4.6", "1.4"),
    "webtoons": ("2522335540328470744", "1.4.57", "1.4"),
    "webtoons_zh_hant": ("2959982438613576472", "1.4.57", "1.4"),
    "manhuashe": ("6230622879116184108", "1.6.1", "1.6"),
    "comicabc": ("8110122805257580230", "1.4.3", "1.4"),
    "flamecomics": ("8531542650987673943", "1.4.50", "1.4"),
    "readblackclovermangaonline": ("6485938153129890061", "1.4.8", "1.4"),
    "readfairytailedenszeromangaonline": ("1330793582354406642", "1.4.9", "1.4"),
    "readjujutsukaisenmangaonline": ("808850989053853006", "1.4.10", "1.4"),
    "readkingdommangaonline": ("7952360835727640966", "1.4.9", "1.4"),
    "readnanatsunotaizai7deadlysinsmangaonline": ("3945031984510180731", "1.4.10", "1.4"),
    "readonepiecemangaonline": ("1061544757733451419", "1.4.8", "1.4"),
    "readsololevelingmangamanhwaonline": ("1374366734159205648", "1.4.10", "1.4"),
    "readtokyoghoulretokyoghoulmangaonline": ("6468833665354206027", "1.4.12", "1.4"),
}


class TestSourceRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_path = repo_root / "sources_registry.json"
        cls.schema_path = (
            repo_root
            / "tools"
            / "source_conversion"
            / "schema"
            / "source_registry.schema.json"
        )
        cls.registry = json.loads(cls.registry_path.read_text(encoding="utf-8"))
        cls.schema = json.loads(cls.schema_path.read_text(encoding="utf-8"))
        cls.artifacts = cls.registry["artifacts"]
        cls.by_id = {item["artifactId"]: item for item in cls.artifacts}

    def test_registry_schema_validation(self):
        result = validate_registry_data(self.registry)
        self.assertEqual(result.errors, ())
        self.assertFalse(self.schema["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["artifact"]["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["upstream"]["additionalProperties"])
        source_id_schema = self.schema["$defs"]["upstream"]["properties"]["sourceId"]
        self.assertEqual(source_id_schema["type"], "string")
        artifact_properties = self.schema["$defs"]["artifact"]["properties"]
        self.assertEqual(artifact_properties["catalogName"]["type"], "string")
        self.assertEqual(artifact_properties["catalogDescription"]["type"], "string")

        invalid = copy.deepcopy(self.registry)
        invalid["artifacts"][0]["typoField"] = True
        self.assertTrue(validate_registry_data(invalid).with_code("SCHEMA_UNKNOWN_FIELD"))

    def test_catalog_metadata_is_optional_string_only(self):
        for field in ("catalogName", "catalogDescription"):
            invalid_type = copy.deepcopy(self.registry)
            invalid_type["artifacts"][0][field] = 42
            errors = validate_registry_data(invalid_type).with_code("SCHEMA_FIELD_TYPE")
            self.assertTrue(any(field in error.message for error in errors), field)

            invalid_empty = copy.deepcopy(self.registry)
            invalid_empty["artifacts"][0][field] = ""
            errors = validate_registry_data(invalid_empty).with_code("SCHEMA_FIELD_VALUE")
            self.assertTrue(any(field in error.message for error in errors), field)

    def test_all_catalog_artifacts_are_registered(self):
        index = json.loads((repo_root / "index.json").read_text(encoding="utf-8"))
        indexed_ids = {Path(entry["fileName"]).stem for entry in index}
        self.assertEqual(len(self.artifacts), 57)
        self.assertEqual(set(self.by_id), indexed_ids)

    def test_artifact_ids_are_unique(self):
        artifact_ids = [item["artifactId"] for item in self.artifacts]
        self.assertEqual(len(artifact_ids), len(set(artifact_ids)))
        self.assertFalse(validate_registry_data(self.registry).with_code("DUPLICATE_ARTIFACT_ID"))

    def test_artifact_id_filename_linkage(self):
        for artifact_id in self.by_id:
            final_path = repo_root / f"{artifact_id}.js"
            self.assertTrue(final_path.is_file(), artifact_id)
            self.assertEqual(final_path.stem, artifact_id)
        result = validate_repository(repo_root)
        self.assertFalse(result.with_code("ARTIFACT_FILE_MISSING"))

    def test_existing_runtime_keys_are_frozen(self):
        actual = {item["artifactId"]: item["runtimeKey"] for item in self.artifacts}
        self.assertEqual(actual, EXPECTED_RUNTIME_KEYS)
        result = validate_repository(repo_root)
        self.assertFalse(result.with_code("RUNTIME_KEY_MISMATCH"))

    def test_copy_manga_shared_runtime_slot_is_explicitly_reported(self):
        result = validate_repository(repo_root)
        reports = result.with_code("SHARED_RUNTIME_KEY")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].severity, "REPORT")
        self.assertEqual(reports[0].subject, "copy_manga")
        self.assertIn("copy_manga_multi_accounts", reports[0].message)
        self.assertFalse(result.with_code("DUPLICATE_RUNTIME_KEY"))

    def test_unique_runtime_key_must_not_declare_shared_group(self):
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [copy.deepcopy(self.by_id["komiic"])],
        }
        registry["artifacts"][0]["compatibility"] = {
            "sharedRuntimeKeyGroup": "copy_manga"
        }

        result = validate_registry_data(registry)

        errors = result.with_code("UNNECESSARY_SHARED_RUNTIME_KEY_GROUP")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, "ERROR")
        self.assertEqual(errors[0].subject, "komiic")

    def test_duplicate_runtime_key_without_group_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["copy_manga"]),
            copy.deepcopy(self.by_id["copy_manga_multi_accounts"]),
        ]
        for artifact in artifacts:
            artifact.pop("compatibility")

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        errors = result.with_code("DUPLICATE_RUNTIME_KEY")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, "ERROR")
        self.assertIn("<missing>", errors[0].message)

    def test_duplicate_runtime_key_with_partial_grouping_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["copy_manga"]),
            copy.deepcopy(self.by_id["copy_manga_multi_accounts"]),
        ]
        artifacts[1].pop("compatibility")

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        self.assertEqual(len(result.with_code("DUPLICATE_RUNTIME_KEY")), 1)
        self.assertEqual(
            len(result.with_code("INVALID_SHARED_RUNTIME_KEY_GROUP")), 1
        )

    def test_shared_group_spanning_different_runtime_keys_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["komiic"]),
            copy.deepcopy(self.by_id["baozi"]),
        ]
        for artifact in artifacts:
            artifact["compatibility"] = {
                "sharedRuntimeKeyGroup": "cross_runtime_group"
            }

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        errors = result.with_code("INVALID_SHARED_RUNTIME_KEY_GROUP")
        self.assertEqual(len(errors), 1)
        self.assertIn("spans runtimeKeys", errors[0].message)
        self.assertEqual(
            len(result.with_code("UNNECESSARY_SHARED_RUNTIME_KEY_GROUP")), 2
        )

    def test_duplicate_runtime_key_split_across_groups_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["copy_manga"]),
            copy.deepcopy(self.by_id["copy_manga_multi_accounts"]),
        ]
        artifacts[0]["compatibility"]["sharedRuntimeKeyGroup"] = "copy_group_a"
        artifacts[1]["compatibility"]["sharedRuntimeKeyGroup"] = "copy_group_b"

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        self.assertEqual(len(result.with_code("DUPLICATE_RUNTIME_KEY")), 1)
        self.assertEqual(
            len(result.with_code("INVALID_SHARED_RUNTIME_KEY_GROUP")), 2
        )

    def test_upstream_source_ids_are_json_strings(self):
        upstream_records = [item["upstream"] for item in self.artifacts if "upstream" in item]
        self.assertEqual(len(upstream_records), 24)
        self.assertTrue(all(isinstance(item["sourceId"], str) for item in upstream_records))

        invalid = copy.deepcopy(self.registry)
        invalid["artifacts"][-1]["upstream"]["sourceId"] = 8531542650987673943
        errors = validate_registry_data(invalid).with_code("SCHEMA_FIELD_VALUE")
        self.assertTrue(any("upstream.sourceId" in error.message for error in errors))

    def test_current_converted_upstream_metadata_anchors(self):
        actual = {
            artifact_id: (
                self.by_id[artifact_id]["upstream"]["sourceId"],
                self.by_id[artifact_id]["upstream"]["version"],
                self.by_id[artifact_id]["upstream"]["extensionLib"],
            )
            for artifact_id in CONVERTED_ARTIFACTS
        }
        self.assertEqual(actual, EXPECTED_CONVERTED_UPSTREAM)

    def test_source_instance_locale_contract(self):
        for locale in ("en", "ja", "all", "fil", "zh-Hans", "zh-Hant", "pt-BR"):
            self.assertTrue(is_bcp47_locale(locale), locale)
        for locale in (
            "zh_Hant",
            "ZH-hant",
            "zh-hans",
            "pt-br",
            "english",
            "",
        ):
            self.assertFalse(is_bcp47_locale(locale), locale)

        invalid = copy.deepcopy(self.registry)
        invalid["artifacts"][-1]["locales"] = ["zh_Hant"]
        self.assertTrue(validate_registry_data(invalid).with_code("INVALID_LOCALE"))

        valid_allar = copy.deepcopy(self.registry)
        valid_allar["artifacts"][-1]["locales"] = ["all"]
        self.assertEqual(validate_registry_data(valid_allar).errors, ())

    def test_locale_omission_empty_and_duplicate_semantics(self):
        artifact = copy.deepcopy(self.by_id["komiic"])
        artifact.pop("locales", None)
        omitted = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": [artifact]}
        )
        self.assertEqual(omitted.errors, ())

        empty = copy.deepcopy(artifact)
        empty["locales"] = []
        self.assertTrue(
            validate_registry_data(
                {"schemaVersion": "1.0", "artifacts": [empty]}
            ).with_code("SCHEMA_FIELD_TYPE")
        )

        duplicate = copy.deepcopy(artifact)
        duplicate["locales"] = ["en", "en"]
        self.assertTrue(
            validate_registry_data(
                {"schemaVersion": "1.0", "artifacts": [duplicate]}
            ).with_code("DUPLICATE_LOCALE")
        )

        locale_schema = self.schema["$defs"]["artifact"]["properties"]["locales"]
        self.assertNotIn("default", locale_schema)
        self.assertNotIn("not", locale_schema["items"])

    def test_content_warning_is_optional_without_a_safe_default(self):
        artifact = copy.deepcopy(self.by_id["komiic"])
        artifact.pop("contentWarning", None)
        omitted = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": [artifact]}
        )
        self.assertEqual(omitted.errors, ())

        for warning in ("SAFE", "MIXED", "NSFW"):
            valid = copy.deepcopy(artifact)
            valid["contentWarning"] = warning
            self.assertEqual(
                validate_registry_data(
                    {"schemaVersion": "1.0", "artifacts": [valid]}
                ).errors,
                (),
                warning,
            )

        for warning in ("safe", "UNKNOWN", None):
            invalid = copy.deepcopy(artifact)
            invalid["contentWarning"] = warning
            self.assertTrue(
                validate_registry_data(
                    {"schemaVersion": "1.0", "artifacts": [invalid]}
                ).with_code("SCHEMA_FIELD_VALUE"),
                warning,
            )

        warning_schema = self.schema["$defs"]["artifact"]["properties"][
            "contentWarning"
        ]
        self.assertNotIn("default", warning_schema)

    def test_upstream_locator_and_snapshot_shape_remains_local_and_compatible(self):
        upstream_schema = self.schema["$defs"]["upstream"]
        self.assertEqual(
            set(upstream_schema["required"]),
            {"project", "module", "sourceId", "version", "extensionLib", "commit"},
        )

        artifact = copy.deepcopy(self.by_id["flamecomics"])
        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": [artifact]}
        )
        self.assertEqual(result.errors, ())

    def test_registry_ir_artifact_linkage(self):
        links = {}
        for ir_path in sorted((repo_root / "sources_ir").glob("*.json")):
            ir = json.loads(ir_path.read_text(encoding="utf-8"))
            links[ir_path.stem] = ir["artifactId"]
        self.assertEqual(set(links), CONVERTED_ARTIFACTS)
        self.assertTrue(all(stem == artifact_id for stem, artifact_id in links.items()))

        result = validate_repository(repo_root)
        linkage_errors = {
            "IR_ARTIFACT_LINK_MISSING",
            "IR_ARTIFACT_FILENAME_MISMATCH",
            "IR_ARTIFACT_UNREGISTERED",
            "DUPLICATE_IR_ARTIFACT_LINK",
            "REGISTRY_IR_LINK_MISSING",
        }
        self.assertFalse([d for d in result.errors if d.code in linkage_errors])

    def test_ir_v0_2_version_schema_compatibility(self):
        schema_path = (
            repo_root
            / "tools"
            / "source_conversion"
            / "schema"
            / "ir_v0_2.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIn("version", schema["properties"])
        self.assertEqual(
            schema["properties"]["version"]["pattern"],
            "^[0-9]+\\.[0-9]+\\.[0-9]+$",
        )
        for artifact_id in ("comicabc", "flamecomics", "manhuashe"):
            ir = json.loads(
                (repo_root / "sources_ir" / f"{artifact_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(validate_ir_data(ir), [], artifact_id)

    def test_index_validation_is_non_writing_and_current_index_is_canonical(self):
        index_path = repo_root / "index.json"
        before = index_path.read_bytes()
        result = validate_repository(repo_root)
        after = index_path.read_bytes()
        self.assertEqual(after, before)
        self.assertEqual(len(result.with_code("INDEX_NAME_MISMATCH")), 0)
        self.assertEqual(len(result.with_code("INDEX_VERSION_MISMATCH")), 0)
        self.assertEqual(len(result.with_code("INDEX_KEY_MISMATCH")), 0)
        self.assertEqual(len(result.with_code("INDEX_DESCRIPTION_MISMATCH")), 0)
        self.assertEqual(len(result.with_code("INDEX_ENTRY_MISSING")), 0)
        self.assertEqual(len(result.with_code("INDEX_ENTRY_EXTRA")), 0)
        self.assertEqual(len(result.with_code("INDEX_ORDER_MISMATCH")), 0)
        self.assertTrue(all(d.severity == "WARNING" for d in result.warnings))

    def test_canonical_catalog_metadata_and_stale_version_regressions(self):
        entries = derive_index(repo_root)
        by_file = {entry["fileName"]: entry for entry in entries}

        expected_names = {
            "bh3": "《崩坏3》IP站",
            "guazimanhua": "瓜子漫画",
            "terrahistoricus": "泰拉记事社",
            "comicabc": "無限動漫",
            "copy_manga_multi_accounts": "拷贝漫画(多账号)",
            "dongmanmanhua_zh_hans": "Dongman Manhua",
            "globalcomix_zh_hans": "GlobalComix",
            "hanman18": "HANMAN18",
            "manhuawu": "漫画屋",
            "mangadex_zh_hans": "MangaDex（简体中文）",
            "mangadex_zh_hant": "MangaDex（繁體中文）",
            "namicomi_zh_hans": "NamiComi（简体中文）",
            "namicomi_zh_hant": "NamiComi（繁體中文）",
            "readblackclovermangaonline": "Read Black Clover Manga Online",
            "readfairytailedenszeromangaonline": "Read Fairy Tail & Edens Zero Manga Online",
            "readjujutsukaisenmangaonline": "Read Jujutsu Kaisen Manga Online",
            "readkingdommangaonline": "Read Kingdom Manga Online",
            "readnanatsunotaizai7deadlysinsmangaonline": "Read Nanatsu no Taizai 7 Deadly Sins Manga Online",
            "readonepiecemangaonline": "Read One Piece Manga Online",
            "readsololevelingmangamanhwaonline": "Read Solo Leveling Manga Manhwa Online",
            "readtokyoghoulretokyoghoulmangaonline": "Read Tokyo Ghoul Re & Tokyo Ghoul Manga Online",
        }

        self.assertEqual(
            {
                artifact_id: artifact["catalogName"]
                for artifact_id, artifact in self.by_id.items()
                if "catalogName" in artifact
            },
            expected_names,
        )
        expected_descriptions = {
            "wnacg": "紳士漫畫漫畫源, 不能使用時請嘗試更換URL",
            "jm": "禁漫天堂漫畫源, 不能使用時請嘗試切換分流",
            "manga_dex": "Account feature is not supported yet.",
            "happy": "中国大陆及日韩IP无法访问，遇到403可以尝试切换其他地区网络",
            "mycomic": "mycomic.com漫画源, 遇到Cloudflare验证请在源设置中登录",
        }
        self.assertEqual(
            {
                artifact_id: artifact["catalogDescription"]
                for artifact_id, artifact in self.by_id.items()
                if "catalogDescription" in artifact
            },
            expected_descriptions,
        )
        self.assertEqual(
            {
                artifact_id: by_file[f"{artifact_id}.js"]["description"]
                for artifact_id in expected_descriptions
            },
            expected_descriptions,
        )

        self.assertEqual(by_file["comicabc.js"]["name"], "無限動漫")
        self.assertEqual(
            by_file["copy_manga_multi_accounts.js"]["name"],
            "拷贝漫画(多账号)",
        )
        self.assertEqual(
            {
                file_name: by_file[file_name]["version"]
                for file_name in (
                    "ehentai.js",
                    "manga_dex.js",
                    "manwaba.js",
                    "lanraragi.js",
                )
            },
            {
                "ehentai.js": "1.2.0",
                "manga_dex.js": "1.1.2",
                "manwaba.js": "1.0.3",
                "lanraragi.js": "1.2.0",
            },
        )

    def test_registry_linkage_does_not_change_generated_or_final_sources(self):
        CHINESE_GENERATED_NO_PATCH = {
            "bh3",
            "guazimanhua",
            "terrahistoricus",
            "mangadex_zh_hans",
            "mangadex_zh_hant",
            "dongmanmanhua_zh_hans",
            "globalcomix_zh_hans",
            "hanman18",
            "manhuawu",
            "namicomi_zh_hans",
            "namicomi_zh_hant",
        }
        E4B_GENERATED_NO_PATCH = {
            "readblackclovermangaonline",
            "readfairytailedenszeromangaonline",
            "readkingdommangaonline",
            "readnanatsunotaizai7deadlysinsmangaonline",
            "readonepiecemangaonline",
            "readsololevelingmangamanhwaonline",
            "readtokyoghoulretokyoghoulmangaonline",
        }
        tracked_paths = []
        for artifact_id in sorted(CONVERTED_ARTIFACTS):
            tracked_paths.extend(
                [
                    repo_root / "sources_generated" / f"{artifact_id}.base.js",
                    repo_root / f"{artifact_id}.js",
                ]
            )
        before = {path: path.read_bytes() for path in tracked_paths}

        for artifact_id in sorted(CONVERTED_ARTIFACTS):
            ir = json.loads(
                (repo_root / "sources_ir" / f"{artifact_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            base_path = repo_root / "sources_generated" / f"{artifact_id}.base.js"
            patch_path = repo_root / "sources_patches" / f"{artifact_id}.patch.js"
            final_path = repo_root / f"{artifact_id}.js"
            generated = generate_venera_js(ir)
            checked_in_base = base_path.read_text(encoding="utf-8")
            checked_in_final = final_path.read_text(encoding="utf-8")
            if artifact_id in CHINESE_GENERATED_NO_PATCH:
                self.assertFalse(patch_path.exists(), artifact_id)
                self.assertEqual(generated, checked_in_base, artifact_id)
                composed = generated
            elif artifact_id in E4B_GENERATED_NO_PATCH:
                self.assertFalse(patch_path.exists(), f"Expected no patch file for {artifact_id}")
                if generated != checked_in_base:
                    self.assertEqual(ir["version"], "1.0.0", artifact_id)
                    self.assertEqual(checked_in_base, checked_in_final, artifact_id)
                    continue
                composed = generated
            else:
                self.assertEqual(generated, checked_in_base, artifact_id)
                composed = patch_js(generated, patch_path.read_text(encoding="utf-8"))
            self.assertEqual(composed, checked_in_final, artifact_id)

        validate_repository(repo_root)
        after = {path: path.read_bytes() for path in tracked_paths}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
