from app import app

# Vercel serverless functions often look for an 'app' instance in 'index.py'
if __name__ == "__main__":
    app.run()
