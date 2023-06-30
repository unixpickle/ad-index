import time
from dataclasses import dataclass
from typing import List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

START_PAGE = "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&sort_data[direction]=desc&sort_data[mode]=relevancy_monthly_grouped&media_type=all"


@dataclass
class SearchResult:
    id: str


class ResultParseError(Exception):
    pass


class Client:
    def __init__(self):
        self.driver = webdriver.Firefox()

    def setup(self):
        self.driver.get(START_PAGE)
        for x in self.driver.find_elements(by=By.TAG_NAME, value="button"):
            if x.get_attribute("title").strip() == "Allow all cookies":
                x.click()
                break
        while not self._click_div("Ad category"):
            time.sleep(1.0)
        while not self._click_div("All ads"):
            time.sleep(1.0)

    def query(self, text: str):
        self.setup()
        elem = self.driver.find_element(
            by=By.CSS_SELECTOR,
            value="input[placeholder='Search by keyword or advertiser']",
        )
        assert elem is not None
        elem.send_keys(text + Keys.RETURN)
        for i in range(5):
            results = self._get_search_results()
            if results is not None:
                return results
            time.sleep(2**i)
        raise ResultParseError("could not extract search results")

    def _click_div(self, content: str) -> bool:
        for x in self.driver.find_elements(
            by=By.XPATH, value=f"//*[text()='{content}']"
        ):
            if x.text.strip() == content:
                x.click()
                return True
        return False

    def _get_search_results(self) -> Optional[List[SearchResult]]:
        results = []
        for id_field in self.driver.find_elements(
            by=By.XPATH, value="//*[starts-with(text(), 'ID: ')]"
        ):
            # main_elem = id_field.find_elements(by=By.XPATH, value='../../../../..')
            results.append(SearchResult(id=id_field.text.split(" ")[-1]))
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


if __name__ == "__main__":
    c = Client()
    print(c.query("lilly pulitzer"))
