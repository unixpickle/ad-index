import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Dict, List, Optional, Sequence

from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver

START_PAGE = "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&sort_data[direction]=desc&sort_data[mode]=relevancy_monthly_grouped&media_type=all"
RETRIES = 5


@dataclass
class SearchResult:
    id: str
    account_name: str
    account_url: str
    start_date: Optional[int]
    text: Optional[str]


class ResultParseError(Exception):
    pass


class Client:
    def __init__(self, driver: WebDriver):
        self.executor = ThreadPoolExecutor(1)
        self.driver = driver

    @classmethod
    @asynccontextmanager
    async def create(cls) -> "Client":
        driver = webdriver.Firefox()
        client = Client(driver)
        try:
            yield client
        finally:
            client.close()

    async def query(self, text: str) -> List[SearchResult]:
        return await asyncio.get_running_loop().run_in_executor(
            self.executor, partial(self._query, text)
        )

    def _query(self, text: str) -> List[SearchResult]:
        self._setup()
        elem = self.driver.find_element(
            by=By.CSS_SELECTOR,
            value="input[placeholder='Search by keyword or advertiser']",
        )
        assert elem is not None
        elem.send_keys(text + Keys.RETURN)
        for i in range(RETRIES):
            results = self._get_search_results()
            if results is not None:
                return results
            time.sleep(2**i)
        raise ResultParseError("could not extract search results")

    async def screenshot_ids(self, ids: Sequence[str]) -> Dict[str, Image.Image]:
        return await asyncio.get_running_loop().run_in_executor(
            self.executor, partial(self._screenshot_ids, ids)
        )

    def _screenshot_ids(self, ids: Sequence[str]) -> Dict[str, Image.Image]:
        main_elem_query = (
            "//*["
            + " or ".join(f"text()='ID: {id}'" for id in ids)
            + "]/../../../../../../.."
        )
        img_query = main_elem_query + "//img"
        complete = True
        for i in range(RETRIES):
            complete = True
            for x in self.driver.find_elements(by=By.XPATH, value=img_query):
                if not x.get_attribute("complete"):
                    complete = False
                    break
            if complete:
                break
            time.sleep(2**i)
        if not complete:
            raise ResultParseError("images never finished loading")

        images = {}
        for main_elem in self.driver.find_elements(by=By.XPATH, value=main_elem_query):
            id_item = main_elem.find_element(
                by=By.XPATH, value="//*[starts-with(text(), 'ID: ')]"
            )
            id = id_item.text.split(" ")[1]
            content = main_elem.find_element(
                by=By.XPATH, value="hr/following-sibling::*"
            )
            images[id] = Image.open(io.BytesIO(content.screenshot_as_png))
        return images

    def _setup(self):
        self.driver.get(START_PAGE)
        for x in self.driver.find_elements(by=By.TAG_NAME, value="button"):
            if x.get_attribute("title").strip() == "Allow all cookies":
                x.click()
                break
        self._click_div("Ad category")
        self._click_div("All ads")

    def _click_div(self, content: str):
        for i in range(RETRIES):
            for x in self.driver.find_elements(
                by=By.XPATH, value=f"//*[text()='{content}']"
            ):
                try:
                    x.click()
                    return
                except ElementClickInterceptedException:
                    pass
                break
            time.sleep(2**i)
        raise ResultParseError(f'could not click div with text: "{content}"')

    def _get_search_results(self) -> Optional[List[SearchResult]]:
        results = []
        for id_field in self.driver.find_elements(
            by=By.XPATH, value="//*[starts-with(text(), 'ID: ')]"
        ):
            main_elem = id_field.find_element(by=By.XPATH, value="../../../../../../..")
            start_date = None
            for x in main_elem.find_elements(
                by=By.XPATH, value="//*[starts-with(text(), 'Started running on')]"
            ):
                date_str = " ".join(x.text.split(" ")[3:])
                date_format = "%b %d, %Y"
                date_obj = datetime.strptime(date_str, date_format).replace(
                    tzinfo=timezone.utc
                )
                start_date = int(date_obj.timestamp())
            sep = main_elem.find_element(by=By.TAG_NAME, value="hr")
            ad_body = self.driver.execute_script(
                "return arguments[0].nextElementSibling;", sep
            )
            account_link = ad_body.find_element(by=By.TAG_NAME, value="a")
            results.append(
                SearchResult(
                    id=id_field.text.split(" ")[-1],
                    account_name=account_link.text,
                    account_url=account_link.get_attribute("href"),
                    start_date=start_date,
                    text=ad_body.text,
                )
            )
        if len(results):
            return results
        elif len(
            self.driver.find_elements(
                by=By.XPATH, value="//*[text()='No ads match your search criteria']"
            )
        ):
            return []
        else:
            return None

    def close(self):
        self.executor.shutdown()
        self.driver.close()


async def main():
    async with Client.create() as c:
        results = await c.query("lilly pulitzer")
        print(len(results), results[0])
        img = (await c.screenshot_ids([results[0].id]))[results[0].id]
        img.save("ad.png")


if __name__ == "__main__":
    asyncio.run(main())
