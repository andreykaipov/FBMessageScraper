import os
import sys
import getopt
import re
import json
import requests

usage = ('Usage: python scrape.py -h header_info_file [-c chunk_size] [-g]'
         'python scrape.py -h my_header')

request_headers = {
    'origin': 'https://www.facebook.com',
    'accept-encoding': 'gzip,deflate',
    'accept-language': 'en-US,en;q=0.8',
    'cookie': '',
    'pragma': 'no-cache',
    'user-agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.107 Safari/537.36',
    'content-type': 'application/x-www-form-urlencoded',
    'accept': '*/*',
    'cache-control': 'no-cache',
    'referer': 'https://www.facebook.com/messages/zuck'
}

def get_user_url(user_id):
    return 'https://www.facebook.com/{}'.format(user_id)

# ..."entity_id":"123456789"...
def get_user_id(user_url):
    return re.search('"entity_id":"(.*?)"', requests.get(user_url).text).group(1)

# ..."name":"Some Dude"...
def get_user_name(user_id):
    user_url = get_user_url(user_id)
    return re.search('"name":"(.*?)"', requests.get(user_url).text).group(1)

def create_dir_for_user(user_id):
    user_name = get_user_name(user_id)
    msg_dir = 'messages/{}'.format(user_name)
    try:
        os.makedirs(msg_dir)
    except OSError:
        pass # already exists
    return msg_dir

# text looks like 'k1:v1\nk2:v2\nk3:v3\n'
def text_into_dict(text):
    d = {}
    for line in text.split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            d[key] = val.split('\n')[0] # remove potential new lines
    return d

def main(argv):
    try:
        options, remainder = getopt.getopt(
            argv,
            'h:c:o:g',
            ['header', 'chunk_size', 'group']
        )
    except getopt.GetoptError as err:
        print(err)
        print(usage)
        sys.exit(2)

    # for 'offset' to properly work as an optarg, we need the
    # appropriate timestamp associated with the message to be offset,
    # which is kinda hard to find without running the script first ... !
    header_info = None
    limit = 1000
    offset = 0
    timestamp = 0
    group_flag = False

    for opt, arg in options:
        if opt in ('-h', '--header'):
            header_info = open(arg).read()
        elif opt in ('-c', '--chunk_size'):
            limit = int(arg)
        elif opt in ('-g', '--group'):
            group_flag = True

    if header_info is None:
        print(usage)
        sys.exit(3)

    form_data = text_into_dict(header_info)
    request_headers.update({
        'cookie': form_data['cookie'],
    })
    my_id = form_data['__user']

    id_type = 'user_ids' if not group_flag else 'thread_fbids'
    friend_id = re.search('messages\[{}\]\[(.*)\]\[.*\]'.format(id_type), header_info).group(1)
    messages_ids = 'messages[{}][{}]'.format(id_type, friend_id)

    form_data.update({
        messages_ids + '[limit]': limit - 1, # subtract 1 because messages are 0 indexed.
    })

    chat_log_directory = create_dir_for_user(friend_id)

    my_name = get_user_name(my_id)
    friend_name = get_user_name(friend_id)
    name_dict = { my_id: my_name, friend_id: friend_name }
    response = ''

    # "oh no that's such bad practice noooooooo"
    while True :

        # update on each scrape
        form_data.update({
            messages_ids + '[offset]': offset,
            messages_ids + '[timestamp]': timestamp
        })

        print('retrieving messages {} to {} with {} ...'.format(offset, limit + offset - 1, friend_name))

        response = requests.post(
            url ='https://www.facebook.com/ajax/mercury/thread_info.php',
            data = form_data,
            headers = request_headers
        )
        response = json.loads(response.text[9:]) # strip the "for (;;);" and get the json.

        chat_log = ''

        if 'actions' in response['payload']:

            previous_author = ''
            previous_timestamp = ''

            # messages[k] is the (limit-k-1)-th oldest,
            # e.g. in the first chunk of say 100 messages, messages[99] will be the most recent message.
            messages = response['payload']['actions']

            for k in range(0, len(messages)):

                message = messages[k]
                author = name_dict[message['author'][5:]] # strip the "fbid:" prefix, and get the name
                timestamp = message['timestamp_datetime']
                body = message['body']

                if previous_author == author and previous_timestamp == timestamp:
                    chat_log += body + '\r\n'
                else:
                    chat_log += '\r\n'
                    chat_log += author + ' at ' + timestamp + '\r\n' + \
                                body + '\r\n'

                previous_author = author
                previous_timestamp = timestamp

            # alter the timestamp to be before the oldest possible one for this chunk
            timestamp = messages[0]['timestamp'] - 1

            outfile = open('{}/{}-{}.txt'.format(chat_log_directory, offset, limit + offset - 1), 'w')
            outfile.write(chat_log)
            outfile.close()

            offset += limit # add

        elif 'end_of_history' in response['payload']:
            print('reached end of history! thanks.')
            break

        else:
            print('oops - something went really wrong. here was the response:')
            print(response)
            sys.exit(3)

        time.sleep(7) # wait x seconds before fetching next set of messages


if __name__ == '__main__':

    if len(sys.argv) <= 1:
        sys.exit()
    main(sys.argv[1:])
