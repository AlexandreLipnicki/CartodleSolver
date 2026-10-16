from starlette.responses import JSONResponse

class BodyLimitMiddleware:
    """Bound uploads before the multipart parser can spool them to disk."""
    def __init__(self,app,max_upload_bytes):
        self.app=app;self.max_upload_bytes=max_upload_bytes
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        limit=self.max_upload_bytes if scope['path'].endswith('/analyze') else 256*1024
        data=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            data.extend(message.get('body',b''))
            if len(data)>limit:
                return await JSONResponse({'detail':'Requête trop volumineuse.'},status_code=413)(scope,receive,send)
            if not message.get('more_body',False):break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True;return {'type':'http.request','body':bytes(data),'more_body':False}
            return await receive()
        return await self.app(scope,replay,send)
