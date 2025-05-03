docker build -t xhongc/photozen-ai .   
docker run -d -p 8010:8060 -v /var/run/docker.sock:/var/run/docker.sock --name photozen-ai photo-ai