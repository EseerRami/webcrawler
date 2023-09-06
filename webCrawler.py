# Importing the required libraries
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Initialize SQLite Database


def initialize_database():
    conn = sqlite3.connect("scraped_links.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS links

                 (url TEXT PRIMARY KEY, visited BOOLEAN)"""
    )
    conn.commit()
    conn.close()


# Store a link in the database
def store_link(link, visited=False):

    conn = sqlite3.connect("scraped_links.db")

    c = conn.cursor()

    c.execute(
        "INSERT OR IGNORE INTO links (url, visited) VALUES (?, ?)", (link, visited)
    )

    conn.commit()

    conn.close()


# Check if a link has been visited


def has_been_visited(link):

    conn = sqlite3.connect("scraped_links.db")

    c = conn.cursor()

    c.execute("SELECT visited FROM links WHERE url = ?", (link,))

    result = c.fetchone()

    conn.close()

    return result[0] if result else False


# Function to start the web scraper with SQLite database integration
def scrape_website(start_url, max_depth=0, max_links=150):
    initialize_database()

    # Initialize Selenium WebDriver
    driver = webdriver.Chrome()

    link_queue = [(start_url, 0)]

    while link_queue:
        current_link, current_depth = link_queue.pop(0)

        if current_depth > max_depth:
            continue

        if has_been_visited(current_link):
            continue

        try:
            driver.get(current_link)

            # Wait for the page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Expand all lists by updating class and style
            driver.execute_script("""
            let lists = document.querySelectorAll('li.oj-typography-body-sm.tree-view-row.oj-vdom-template-root.oj-treeview-item.oj-collapsed');
            for (let item of lists) {
                item.classList.remove('oj-collapsed');
                item.classList.add('oj-expanded');
                let ulElement = item.querySelector('ul.oj-treeview-list');
                if (ulElement) {
                    ulElement.style.display = 'block';
                }
            }
            """)

            # Wait for a moment to allow the content to load
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")

        except Exception as e:
            print(f"Failed to fetch {current_link}: {e}")
            continue

        links = [
            urljoin(current_link, a["href"]) for a in soup.find_all("a", href=True)
        ]

        store_link(current_link, visited=True)
        print(
            f"Visited {current_link} (Depth: {current_depth}, Queue: {len(link_queue)})"
        )

        for link in links:
            if not has_been_visited(link):
                link_queue.append((link, current_depth + 1))
                store_link(link, visited=False)

        # Check if link limit has been reached

        conn = sqlite3.connect("scraped_links.db")

        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM links WHERE visited = 1")

        visited_count = c.fetchone()[0]

        conn.close()

        if visited_count >= max_links:

            break

        # Rate limiting: Pause for a short while to respect the website's terms

        time.sleep(1)

        # Close the WebDriver
    driver.quit()

# Retrieve and print all stored links from the database
def retrieve_links():
    conn = sqlite3.connect('scraped_links.db')
    c = conn.cursor()
    c.execute("SELECT * FROM links")
    rows = c.fetchall()
    for row in rows:
        print(f"URL: {row[0]}, Visited: {row[1]}")
    conn.close()    


# Test the scraper
if __name__ == "__main__":
    start_url = "https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/23c/oedsc/cseassetsb-24399.html"  # Oracle Docs URL
    scrape_website(
        start_url, max_depth=0, max_links=150
    )  # Limiting depth and number of links
    # Retrieve and print all stored links
    print("Retrieving all stored links:")
    retrieve_links()