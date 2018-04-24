FROM ubuntu:xenial

RUN apt-get update && apt install -y build-essential \
    curl autoconf bison build-essential libssl-dev libyaml-dev \
    libreadline6-dev zlib1g-dev libncurses5-dev libffi-dev \
    libgdbm3 libgdbm-dev && curl -sL https://deb.nodesource.com/setup_8.x | bash - && \
    curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add - && \
    echo "deb https://dl.yarnpkg.com/debian/ stable main" | \
    tee /etc/apt/sources.list.d/yarn.list && apt-get update && \
    apt install -y git-core curl zlib1g-dev build-essential libssl-dev libreadline-dev libyaml-dev libsqlite3-dev sqlite3 libxml2-dev libxslt1-dev libcurl4-openssl-dev python-software-properties libffi-dev nodejs yarn && \
    cd && git clone https://github.com/rbenv/rbenv.git ~/.rbenv && \
    echo 'export PATH="$HOME/.rbenv/bin:$PATH"' >> ~/.bashrc && \
    echo 'eval "$(rbenv init -)"' >> ~/.bashrc && exec $SHELL && \
    git clone https://github.com/rbenv/ruby-build.git ~/ruby-build && \
    echo 'export PATH="$HOME/ruby-build/bin:$PATH"' >> ~/.bashrc && \
    exec $SHELL && rbenv install 2.5.0 && rbenv global 2.5.0 && \
    gem install bundler && \
    curl -o- https://raw.githubusercontent.com/creationix/nvm/v0.33.8/install.sh | bash && \
    export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" && \
    nvm install 7.10.1

     

