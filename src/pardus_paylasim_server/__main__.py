"""`python -m pardus_paylasim_server` giriş noktası."""

import asyncio

from pardus_paylasim_server.router import main

if __name__ == "__main__":
    asyncio.run(main())
