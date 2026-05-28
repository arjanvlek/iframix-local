"""Download page handler methods (app package info)."""


class DownloadMixin:

    def handle_package_project(self, params):
        """Return app package info for the download page."""
        self.respond_json({
            "code": 1,
            "msg": "success",
            "data": {
                "project_name": "iFramixPro",
                "icon": "https://down.codethriving.com/default//iframix_pro.png/iframix_pro.png",
                "url": "https://ifp.ga.codethriving.com/download",
                "more": {
                    "is_qiniu": "0"
                },
                "desc": [],
                "items": [
                    {
                        "store_type": "android",
                        "store_address": "",
                        "version": "2.2.29",
                        "num_version": 87,
                        "updated_at": "2026-02-17",
                        "download_address": "https://down.codethriving.com/default/APP/FOCASE/iFramixPro/iFramix_Pro_2.2.29.apk"
                    },
                    {
                        "store_type": "ios",
                        "store_address": "https://apps.apple.com/us/app/iframix-pro/id6470332689",
                        "version": "2.2.29",
                        "num_version": 87,
                        "updated_at": "2026-02-17",
                        "download_address": None
                    }
                ]
            }
        })
