# Unitest format from PY175 CMS to adapt...

import unittest
import os
import sys
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app


class AppTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.data_path = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(self.data_path, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.data_path, ignore_errors=True)

    def create_document(self, name, contents=""):
        with open(os.path.join(self.data_path, name), 'w') as file:
            file.write(contents)

    def test_index(self):

        self.create_document("about.md")
        self.create_document("changes.txt")
        with self.client.get("/") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "text/html; charset=utf-8")

            files = [os.path.basename(file) for file in os.listdir(self.data_path)]
            in_response = all([True if file in response.get_data(as_text=True) else False for file in files])

            self.assertTrue(in_response)

    def test_get_file(self):
        self.create_document('history.txt', "Python 0.9.0 (initial release) is released.")
        with self.client.get('/history.txt') as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "text/plain; charset=utf-8")
            self.assertIn("Python 0.9.0 (initial release) is released.", response.get_data(as_text=True))

    def test_document_not_found(self):
        # Attempt to access a nonexistent file and verify a redirect happens
        with self.client.get("/notafile.ext") as response:
            self.assertEqual(response.status_code, 302)

        # Verify redirect and message handling works
        with self.client.get(response.headers['Location']) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("notafile.ext does not exist",
                          response.get_data(as_text=True))

        # Assert that a page reload removes the message
        with self.client.get("/") as response:
            self.assertNotIn("notafile.ext does not exist",
                             response.get_data(as_text=True))
            
    def test_view_markdown(self):
        self.create_document('about.md', "# Python is...")
        response = self.client.get('/about.md')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertIn("<h1>Python is...</h1>", response.get_data(as_text=True))

    def test_edit_file(self):
        self.create_document("changes.txt")
        client = self.admin_session()
        response = client.get('/changes.txt/edit')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertIn("<textarea", response.get_data(as_text=True))

    def test_updating_file(self):
        self.create_document("changes.txt")
        client = self.admin_session()
        response = client.post('/changes.txt/edit', data={'content': "new content"})
        self.assertEqual(response.status_code, 302)

        follow_response = client.get(response.headers['Location'])
        self.assertIn("changes.txt has been updated.", follow_response.get_data(as_text=True))

        with client.get("/changes.txt") as content_response:
            self.assertEqual(content_response.status_code, 200)
            self.assertIn("new content", content_response.get_data(as_text=True))      

    def test_enter_new_document(self):
        client = self.admin_session()
        response = client.get('/new')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertIn("<form action=\"/new\" method=\"post\">", response.get_data(as_text=True))

    def test_save_new_document(self):
        client = self.admin_session()
        response = client.post("/new", data={'new_file': "new_file.txt"})
        self.assertEqual(response.status_code, 302)
        follow_response = client.get(response.headers['Location'])
        self.assertIn("new_file.txt has been created.", follow_response.get_data(as_text=True))

        with client.get("/new_file.txt") as content_response:
            self.assertEqual(content_response.status_code, 200)

    def test_create_new_document_without_filename(self):
        client = self.admin_session()
        response = client.post('/new', data={'new_file': ''})
        self.assertEqual(response.status_code, 422)
        self.assertIn("A name is required.", response.get_data(as_text=True))

    def test_deleting_document(self):
        self.create_document("test.txt")
        client = self.admin_session()
        response = client.post('/test.txt/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("test.txt has been deleted",
                      response.get_data(as_text=True))

        response = client.get('/')
        self.assertNotIn("test.txt", response.get_data(as_text=True))

    def test_signin_form(self):
        client = self.admin_session()
        response = client.get('/users/signin')
        self.assertEqual(response.status_code, 200)
        self.assertIn("<input", response.get_data(as_text=True))
        self.assertIn('<button type="submit"', response.get_data(as_text=True))

    def test_signin(self):
        response = self.client.post('/users/signin',
                                    data={
                                        'username': 'admin',
                                        'password': 'secret',
                                    },
                                    follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Welcome", response.get_data(as_text=True))
        self.assertIn("Signed in as admin", response.get_data(as_text=True))

    def test_signin_with_bad_credentials(self):
        response = self.client.post('/users/signin',
                                    data={
                                        'username': 'guest',
                                        'password': 'shhhh',
                                    })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Invalid credentials", response.get_data(as_text=True))

    def test_signout(self):
        self.client.post('/users/signin',
                         data={'username': 'admin', 'password': 'secret'},
                         follow_redirects=True)
        response = self.client.post('/users/signout', follow_redirects=True)
        self.assertIn("You have been signed out",
                      response.get_data(as_text=True))
        self.assertIn("Sign In", response.get_data(as_text=True))

    def admin_session(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess['username'] = 'admin'
            return c

    def test_require_login_routes(self):
        self.create_document("test.txt")
        resonse = self.client.get("/test.txt/edit")
        self.assertEqual(resonse.status_code, 302)
        response = self.client.post("/test.txt/edit", data={'content':'new content'})
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/new")
        self.assertEqual(response.status_code, 302)
        response = self.client.post("/new", data={'new_file': 'new_file.txt'})
        self.assertEqual(response.status_code, 302)
        response = self.client.post("/test.txt/delete")
        self.assertEqual(response.status_code, 302)
        self.admin_session()
        response = self.client.post("/test.txt/delete")
        self.assertEqual(response.status_code, 302)

if __name__ == '__main__':
    unittest.main()