
class Blob:
  def __init__(self, fname, bucket, *args, **kwargs):
    print ('fu {} {} {}'.format(fname, args, kwargs))
    self._fname = fname
    pass

  def upload_from_file(self, file_storage):
    file_storage.save('/tmp/halite/{}'.format(self._fname))
    pass

class Bucket:
  def __init__(self, *args, **kwargs):
    print('Bucket')
    self._args = args
    self._kwargs = kwargs

class Client:
  def __init__(self, *args, **kwargs):
    pass

  def get_bucket(self, *args, **kwargs):
    return Bucket(*args, **kwargs)
