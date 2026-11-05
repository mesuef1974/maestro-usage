var NS="http://www.w3.org/2000/svg";
var MCOL=["--s1","--s2","--s3","--s4","--s5","--s6","--oth"];
var ORIG_AR={human:"إنسان",peer:"جلسة أخرى (peer)",scheduled:"مجدول",sdk:"SDK",task_notification:"إشعار مهمة",system:"نظام",sub:"وكيل فرعي",unknown:"بلا أصل مسجّل"};
/* قالب واحد يخدم عدّة صفحات تحذف أقسامًا: العنصر الغائب يُرجَع عنصرًا وهميًّا غير مربوط فتمرّ الكتابة فيه دون خطأ */
/* الحمولة الكبيرة تُضمَّن بصيغة أعمدة {"$cols":[مفاتيح],"rows":[[قيم]]} لتقليل الحجم؛ تُعاد هنا إلى قائمة كائنات */
function unpack(d){Object.keys(d).forEach(function(k){var v=d[k];if(v&&v.$cols){var c=v.$cols;d[k]=v.rows.map(function(r){var o={};for(var i=0;i<c.length;i++)o[c[i]]=r[i];return o})}});return d}
var $=function(s,r){return (r||document).querySelector(s)||document.createElement("div")};
function css(v){return "var("+v+")"}

/* ---------- أدوات ---------- */
function num(n,d){if(n==null||isNaN(n))return "—";return Number(n).toLocaleString("en-US",{maximumFractionDigits:d||0,minimumFractionDigits:d||0})}
function compact(n,d){
  if(n==null||isNaN(n))return "—";var a=Math.abs(n),s;
  if(a>=1e9)s=(n/1e9).toFixed(a>=1e10?0:(d==null?1:d))+" مليار";
  else if(a>=1e6)s=(n/1e6).toFixed(a>=1e7?0:(d==null?1:d))+" مليون";
  else if(a>=1e3)s=(n/1e3).toFixed(a>=1e4?0:(d==null?1:d))+" ألف";
  else s=String(Math.round(n));
  return s.replace(/\.0 /," ");
}
function pct(x,d){return x==null||isNaN(x)?"—":(100*x).toFixed(d==null?1:d)+"%"}
function ymd(ms){return new Date(ms).toISOString().slice(0,10)}
function dm(day){return Number(day.slice(8,10))+"/"+Number(day.slice(5,7))}
function eachDay(a,b){var out=[],t=Date.parse(a+"T00:00:00Z"),e=Date.parse(b+"T00:00:00Z");for(;t<=e;t+=864e5)out.push(ymd(t));return out}
function addDays(day,n){return ymd(Date.parse(day+"T00:00:00Z")+n*864e5)}
function mk(tag,attrs,text){var e=document.createElement(tag);if(attrs)for(var k in attrs)e.setAttribute(k,attrs[k]);if(text!=null)e.textContent=text;return e}
/* جدول موحَّد للصفحات: رأس ثم صفوف؛ الأرقام تُنسَّق بـnum وتأخذ الصنف num، والنص يبقى كما هو */
function dataTable(box,head,rows){
  var t=mk("table"),hr=t.createTHead().insertRow(),b=t.createTBody();
  head.forEach(function(x){hr.appendChild(mk("th",null,x))});
  rows.forEach(function(r){var tr=b.insertRow();r.forEach(function(v,i){var c=mk("td",i?{"class":"num"}:null,typeof v==="number"?num(v):v);tr.appendChild(c)})});
  box.textContent="";box.appendChild(t);return t;
}
function sv(tag,attrs,text){
  var e=document.createElementNS(NS,tag);if(attrs)for(var k in attrs)e.setAttribute(k,attrs[k]);
  /* الصفحة RTL فيُقلب معنى start/end في نصوص SVG؛ تُكتب المواضع هنا بمعناها الفيزيائي (end = حافة النص اليمنى) ويُبدَّل عند الإنشاء */
  if(tag==="text"){var a=e.getAttribute("text-anchor");if(a==="end")e.setAttribute("text-anchor","start");else if(a==="start")e.setAttribute("text-anchor","end")}
  if(text!=null)e.textContent=text;return e}
function niceMax(v){ /* أربع فترات شبكة بخطوة «نظيفة» (1 أو 1.5 أو 2 أو 3 أو 4 أو 5 أو 6 أو 8 × 10^n) فتخرج العلامات 0 و1 و2 و3 و4 بدل 1.3 و3.8 */
  if(v<=0)return 4;var s=v/4,p=Math.pow(10,Math.floor(Math.log10(s))),f=s/p;
  /* مضاعفات بخانة عشرية واحدة على الأكثر (1 و1.5 و2 و3 و4 و5 و6 و8) فلا يتضخّم المحور حتى الضعف ولا تظهر علامات بكسور لا تُعرض كاملة */
  var n=[1,1.5,2,3,4,5,6,8,10].filter(function(c){return f<=c+1e-9})[0];return 4*n*p}
function clear(e){while(e.firstChild)e.removeChild(e.firstChild)}

/* ---------- تلميح ---------- */
var tip=$("#tip");
function showTip(x,y,title,rows){
  clear(tip);tip.appendChild(mk("div",{class:"h"},title));
  rows.forEach(function(r){
    var d=mk("div",{class:"r"});
    if(r.color){var k=mk("span",{class:"k"});k.style.background=r.color;d.appendChild(k)}
    d.appendChild(mk("span",{class:"nm"},r.name));d.appendChild(mk("b",null,r.value));tip.appendChild(d);
  });
  tip.style.display="block";
  var w=tip.offsetWidth,h=tip.offsetHeight,vw=window.innerWidth,vh=window.innerHeight;
  var left=x+14;if(left+w>vw-8)left=x-w-14;if(left<8)left=8;
  var top=y+14;if(top+h>vh-8)top=y-h-14;if(top<8)top=8;
  tip.style.left=left+"px";tip.style.top=top+"px";
}
function hideTip(){tip.style.display="none"}

/* ---------- رسم عمودي مكدّس (1) ---------- */
function chartW(box){return Math.max(280,Math.floor(box.clientWidth||600))}
function attachNav(svg,n,onShow,onHide){
  svg.setAttribute("tabindex","0");var cur=-1;
  svg.addEventListener("keydown",function(e){
    if(e.key==="ArrowLeft"||e.key==="ArrowRight"||e.key==="Home"||e.key==="End"){
      e.preventDefault();
      if(e.key==="Home")cur=0;else if(e.key==="End")cur=n-1;
      else cur=cur<0?(e.key==="ArrowRight"?n-1:0):Math.max(0,Math.min(n-1,cur+(e.key==="ArrowRight"?1:-1)));
      onShow(cur,null);
    }else if(e.key==="Escape"){onHide()}
  });
  svg.addEventListener("blur",onHide);
}
function drawStack(box,days,series,today,label,tf){
  tf=tf||function(v){return compact(v,2)};
  clear(box);
  var W=chartW(box),H=W<480?240:300,ml=58,mr=8,mt=10,mb=26;
  var totals=days.map(function(_,i){return series.reduce(function(a,s){return a+s.v[i]},0)});
  var ymax=niceMax(Math.max.apply(null,totals.concat([1])));
  var iw=W-ml-mr,ih=H-mt-mb,band=iw/days.length,bw=Math.min(24,Math.max(2,band*.72));
  var svg=sv("svg",{width:W,height:H,viewBox:"0 0 "+W+" "+H,role:"group","aria-label":(label||"أعمدة يومية")+"؛ استعمل الأسهم للتنقل بين الأيام"});
  var yv=function(v){return mt+ih-ih*v/ymax};
  for(var g=0;g<=4;g++){var v=ymax*g/4,y=yv(v);
    svg.appendChild(sv("line",{x1:ml,x2:W-mr,y1:y,y2:y,class:g?"grid":"axis"}));
    svg.appendChild(sv("text",{x:ml-6,y:y+4,"text-anchor":"end"},compact(v,v>=1e9&&v%1e9?1:0)));}
  var hov=sv("rect",{class:"hov",y:mt,height:ih,width:band,x:-99,visibility:"hidden"});svg.appendChild(hov);
  days.forEach(function(d,i){
    var cx=ml+band*i+band/2,x=cx-bw/2,acc=0;
    var visible=series.filter(function(s){return s.v[i]>0});
    visible.forEach(function(s,j){
      var h0=ih*acc/ymax,h1=ih*(acc+s.v[i])/ymax,top=mt+ih-h1,hgt=Math.max(1,h1-h0-(j<visible.length-1?2:0));
      var r=j===visible.length-1?Math.min(4,bw/2,hgt):0,bot=mt+ih-h0-(j<visible.length-1?0:0);
      var y2=bot-hgt;
      var p="M"+x+","+bot+"V"+(y2+r)+(r?"Q"+x+","+y2+" "+(x+r)+","+y2+"H"+(x+bw-r)+"Q"+(x+bw)+","+y2+" "+(x+bw)+","+(y2+r):"V"+y2+"H"+(x+bw))+"V"+bot+"Z";
      svg.appendChild(sv("path",{d:p,fill:css(s.c)}));acc+=s.v[i];
    });
  });
  var step=Math.max(1,Math.ceil(days.length/Math.max(2,Math.floor(iw/62))));
  days.forEach(function(d,i){if(i%step===0||i===days.length-1&&i%step>step/2)svg.appendChild(sv("text",{x:ml+band*i+band/2,y:H-8,"text-anchor":"middle"},dm(d)))});
  function show(i,ev){
    hov.setAttribute("x",ml+band*i);hov.setAttribute("visibility","visible");
    var rect=svg.getBoundingClientRect(),cx=rect.left+ml+band*i+band/2,cy=ev?ev.clientY:rect.top+mt+20;
    var rows=series.filter(function(s){return s.v[i]>0}).reverse().map(function(s){return {color:css(s.c),name:s.name,value:tf(s.v[i])}});
    rows.push({name:"المجموع",value:tf(totals[i])});
    showTip(ev?ev.clientX:cx,cy,days[i]+(days[i]===today?" (اليوم، ناقص)":""),rows);
  }
  function off(){hov.setAttribute("visibility","hidden");hideTip()}
  svg.addEventListener("pointermove",function(e){var r=svg.getBoundingClientRect(),x=e.clientX-r.left-ml,i=Math.floor(x/band);
    if(x<0||i<0||i>=days.length)return off();show(i,e)});
  svg.addEventListener("pointerleave",off);
  attachNav(svg,days.length,show,off);
  box.appendChild(svg);
}

/* ---------- رسم خطي عام (3 و5) ---------- */
function drawLines(box,o){
  clear(box);
  var W=chartW(box),ml=o.ml||52,mr=o.endLabel?44:14,mb=26,iw=W-ml-mr;
  var xs=o.xs,x0=o.x0,x1=o.x1,ymax=o.ymax;
  var X=function(v){return ml+(x1===x0?iw/2:iw*(v-x0)/(x1-x0))};
  /* شارات العلامات المرقّمة (num): تُرصّ في صفوف فوق الرسم؛ شارة تتراكب مع سابقتها تنزل صفًّا، ولا تُقصّ عند الحافتين، والرسم ينزل بقدر الصفوف */
  var mks=o.markers||(o.marker?[o.marker]:[]),rowEnd=[];
  var badges=mks.filter(function(m){return m.num!=null}).map(function(m){var w=Math.max(18,String(m.num).length*7+8);return {m:m,w:w,cx:Math.min(W-mr-w/2,Math.max(ml+w/2,X(m.x)))}}).sort(function(a,b){return a.cx-b.cx});
  badges.forEach(function(b){var r=0;while(r<rowEnd.length&&b.cx-b.w/2<rowEnd[r]+3)r++;rowEnd[r]=b.cx+b.w/2;b.row=r});
  var rows=rowEnd.length,mt=14+18*rows,H=(W<480?220:260)+18*rows,ih=H-mt-mb,Y=function(v){return mt+ih-ih*v/ymax};
  var svg=sv("svg",{width:W,height:H,viewBox:"0 0 "+W+" "+H,role:"group","aria-label":o.label+"؛ استعمل الأسهم للتنقل بين النقاط"});
  for(var g=0;g<=4;g++){var v=ymax*g/4,y=Y(v);
    svg.appendChild(sv("line",{x1:ml,x2:W-mr,y1:y,y2:y,class:g?"grid":"axis"}));
    svg.appendChild(sv("text",{x:ml-6,y:y+4,"text-anchor":"end"},o.yfmt(v)))}
  var nt=Math.max(2,Math.min(6,Math.floor(iw/90)));
  for(var k=0;k<nt;k++){var xv=x0+(x1-x0)*k/(nt-1);if(x1===x0&&k)break;
    svg.appendChild(sv("text",{x:X(xv),y:H-8,"text-anchor":"middle"},o.xfmt(xv)))}
  (o.vlines||[]).forEach(function(vl){var vx=X(vl.x);if(vx<ml||vx>W-mr)return; /* خطوط رأسية خافتة (مثل تصفير النافذة) */
    svg.appendChild(sv("line",{x1:vx,x2:vx,y1:mt,y2:mt+ih,stroke:css("--ink3"),"stroke-width":1,"stroke-dasharray":"3 4",opacity:.7}))});
  /* العلامات: نص بجانب الخط حين تكون قليلة، أو شارة مرقّمة أعلى الخط (num) حين تكثر فلا تتكدّس النصوص فوق الرسم؛ القائمة المرقّمة تحت الرسم */
  mks.forEach(function(mk2,qi){var mx=X(mk2.x);
    var la={x1:mx,x2:mx,y1:mt,y2:mt+ih,stroke:css("--ink"),"stroke-width":1};if(qi||mk2.num!=null)la["stroke-dasharray"]="4 3";
    if(mk2.num!=null){var b=badges.filter(function(x){return x.m===mk2})[0],by=4+18*b.row;la.opacity=.55;la.y1=by+16;
      svg.appendChild(sv("line",la));
      var g=sv("g",{class:"mkb"});
      g.appendChild(sv("rect",{x:b.cx-b.w/2,y:by,width:b.w,height:16,rx:8,style:"fill:var(--surface);stroke:var(--ink2)"}));
      g.appendChild(sv("text",{x:b.cx,y:by+12,"text-anchor":"middle",style:"fill:var(--ink);font-size:10px"},"⁦"+mk2.num+"⁩")); /* عزل LTR كي لا ينقلب «1–9» في RTL */
      var tt=sv("title");tt.textContent=mk2.label||String(mk2.num);g.appendChild(tt);svg.appendChild(g);return}
    svg.appendChild(sv("line",la));
    var tx=sv("text",{x:mx+(mx>W/2?-6:6),y:mt+11+13*qi,"text-anchor":mx>W/2?"end":"start",style:"fill:var(--ink)"},mk2.label);svg.appendChild(tx)});
  var cross=sv("line",{y1:mt,y2:mt+ih,stroke:css("--ink3"),"stroke-width":1,visibility:"hidden"});svg.appendChild(cross);
  var ends=[];
  o.series.forEach(function(s){
    var d="",pen=false;
    var prev=null;
    xs.forEach(function(xv,i){var v=s.v[i];if(v==null){pen=false;return}
      if(o.gap&&prev!=null&&xv-prev>o.gap)pen=false; /* فجوة أطول من الحدّ (نوم الحاسوب مثلًا): الخط ينقطع ولا يصل ما لم يُقَس */
      d+=(pen?"L":"M")+X(xv)+","+Y(v);pen=true;prev=xv});
    svg.appendChild(sv("path",{d:d,fill:"none",stroke:css(s.c),"stroke-width":2,"stroke-linejoin":"round","stroke-linecap":"round"}));
    var last=-1;
    xs.forEach(function(xv,i){var v=s.v[i];if(v==null)return;last=i;
      var hollow=s.hollow&&s.hollow[i];
      svg.appendChild(sv("circle",{cx:X(xv),cy:Y(v),r:4,fill:hollow?css("--surface"):css(s.c),stroke:hollow?css(s.c):css("--surface"),"stroke-width":hollow?2:2}))});
    if(o.endLabel&&last>=0)ends.push({x:X(xs[last])+9,y:Y(s.v[last])+4,t:o.endLabel(s.v[last])});
  });
  ends.sort(function(a,b){return a.y-b.y}); /* تُباعَد التسميتان رأسيًّا عند التصاقهما (فارق أدنى 13 بكسل) */
  for(var q=1;q<ends.length;q++)if(ends[q].y-ends[q-1].y<13){var m=(13-(ends[q].y-ends[q-1].y))/2;ends[q-1].y-=m;ends[q].y+=m}
  ends.forEach(function(e){svg.appendChild(sv("text",{x:e.x,y:e.y,"text-anchor":"start",style:"fill:var(--ink)"},e.t))});
  function show(i,ev){
    var cx=X(xs[i]);cross.setAttribute("x1",cx);cross.setAttribute("x2",cx);cross.setAttribute("visibility","visible");
    var r=svg.getBoundingClientRect();
    var rows=o.series.filter(function(s){return s.v[i]!=null}).map(function(s){return {color:css(s.c),name:s.name,value:o.tfmt(s.v[i])}});
    showTip(ev?ev.clientX:r.left+cx,ev?ev.clientY:r.top+mt+20,o.title(i),rows);
  }
  function off(){cross.setAttribute("visibility","hidden");hideTip()}
  svg.addEventListener("pointermove",function(e){
    var r=svg.getBoundingClientRect(),px=e.clientX-r.left,best=0,bd=1e9;
    xs.forEach(function(xv,i){var dd=Math.abs(X(xv)-px);if(dd<bd){bd=dd;best=i}});show(best,e)});
  svg.addEventListener("pointerleave",off);
  attachNav(svg,xs.length,show,off);
  box.appendChild(svg);
}

/* ---------- جداول قابلة للترتيب ---------- */
function drawTable(box,cols,rows,st,onSort,selFn){
  clear(box);
  var t=mk("table"),th=mk("thead"),tr=mk("tr");
  cols.forEach(function(c){
    var h=mk("th",{scope:"col"});
    if(onSort){h.setAttribute("aria-sort",st&&st.k===c.k?(st.d>0?"ascending":"descending"):"none");
      var b=mk("button",{type:"button"},c.l);b.addEventListener("click",function(){onSort(c.k)});h.appendChild(b)}
    else h.textContent=c.l;
    tr.appendChild(h)});
  th.appendChild(tr);t.appendChild(th);
  var tb=mk("tbody");
  rows.forEach(function(r){var row=mk("tr",selFn&&selFn(r)?{class:"sel"}:null);
    cols.forEach(function(c){var td=mk("td",c.n?{class:"num"}:null);if(c.el)td.appendChild(c.el(r));else td.textContent=c.f?c.f(r):String(r[c.k]);row.appendChild(td)});tb.appendChild(row)});
  t.appendChild(tb);box.appendChild(t);
}
function sortRows(rows,k,d,numeric){
  return rows.slice().sort(function(a,b){var x=a[k],y=b[k];
    if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;
    return (typeof x==="number"&&typeof y==="number"?x-y:String(x).localeCompare(String(y),"ar"))*d})
}

function barRows(box,items,color){
  clear(box);
  if(!items.length){box.appendChild(mk("div",{class:"empty"},"لا بيانات في هذه الفترة."));return}
  var mx=Math.max.apply(null,items.map(function(i){return i.val}))||1;
  items.forEach(function(it){
    var r=mk("div",{class:"brow"+(it.on?" sel":""),tabindex:"0"});
    if(it.pick){r.style.cursor="pointer";r.setAttribute("role","button");r.addEventListener("click",it.pick);r.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();it.pick()}})}
    r.appendChild(mk("div",{class:"n"},it.name));
    var t=mk("div",{class:"t"}),f=mk("div",{class:"f"});f.style.width=(100*it.val/mx)+"%";f.style.background=css(color);t.appendChild(f);r.appendChild(t);
    r.appendChild(mk("div",{class:"x"},it.text));
    function on(e){var rc=r.getBoundingClientRect();showTip(e&&e.clientX!=null?e.clientX:rc.left+rc.width/2,e&&e.clientY!=null?e.clientY:rc.top+rc.height,it.name,it.tip)}
    r.addEventListener("pointermove",on);r.addEventListener("pointerleave",hideTip);r.addEventListener("focus",function(){on(null)});r.addEventListener("blur",hideTip);
    box.appendChild(r);
  });
}

function age(){
  var g=new Date($("#gen").textContent.trim().replace(" ","T")).getTime(),a=$("#age");
  if(isNaN(g)){a.textContent="";return}
  var m=(Date.now()-g)/6e4;
  a.textContent="عمر البيانات: "+(m<1?"أقل من دقيقة":Math.round(m)+" دقيقة")+(m>30?" — قديمة، اضغط تحديث فوري":"");
  a.className=m>30?"warn":"sub";
}
var AUTO={key:"mu_auto",steps:[0,5,15,30],save:null,timer:null,due:0};  // التحديث الدوري: دقائق، 0 = إيقاف؛ يُحفظ في localStorage ويشترك فيه كل الصفحات
function autoGet(){try{var v=Number(localStorage.getItem(AUTO.key));return AUTO.steps.indexOf(v)>0?v:0}catch(e){return 0}}
function refreshNow(msg,b){
  // دورة تحميل كاملة في الخادم ثم إعادة تحميل الصفحة مع حفظ المرشِّحات (زر «تحديث فوري» والدوري كلاهما هنا)
  if(!msg||!b)return;  // صفحةٌ بلا زرّ «تحديث فوري» (مثل «طلب جديد»): لا شيء يُحدَّث ولا خطأ عند العودة إلى التبويب
  if(AUTO.save)AUTO.save();
  if(location.protocol==="file:"){
    msg.textContent="التحديث الفوري يحتاج الخادم المحلي: شغّل python src\\serve.py ثم افتح العنوان 127.0.0.1:8790 في المتصفح — الآن يُعاد تحميل الملف فقط.";
    setTimeout(function(){location.reload()},2500);return}
  b.disabled=true;msg.textContent="جارٍ التحديث…";
  /* الخادم ينتظر الدورة المجدولة إن كانت تعمل (حتى 4 دقائق) ثم يبني؛ بعد 15 ثانية نوضّح سبب الطول بدل صمت الزر */
  var slow=setTimeout(function(){msg.textContent="ما زالت الدورة تعمل (قد تنتظر الدورة المجدولة أو بناء التقارير، حتى 4 دقائق)…"},15000);
  fetch("/refresh",{method:"POST"}).then(function(r){return r.json()}).then(function(j){
    clearTimeout(slow);
    if(j&&j.ok)location.reload();
    else if(j&&j.busy){msg.textContent="دورة أخرى تعمل منذ أكثر من 4 دقائق؛ أعد المحاولة لاحقًا أو راجع data\\cycle.log";b.disabled=false}
    else{msg.textContent="فشلت الدورة؛ راجع data\\cycle.log";b.disabled=false}
  }).catch(function(){clearTimeout(slow);msg.textContent="تعذّر الوصول إلى الخادم المحلي؛ شغّل python src\\serve.py";b.disabled=false});
}
function autoArm(){
  // يعيد ضبط المؤقّت وفق الاختيار المحفوظ؛ التبويب المخفي لا يحدِّث، وتُنفَّذ الدورة المستحقّة عند عودته
  if(AUTO.timer){clearTimeout(AUTO.timer);AUTO.timer=null}
  var m=autoGet();if(!m||location.protocol==="file:")return;
  AUTO.due=Date.now()+m*6e4;
  AUTO.timer=setTimeout(function(){AUTO.timer=null;if(document.hidden){AUTO.due=0;return}refreshNow($("#rmsg"),$("#refresh"))},m*6e4);
}
document.addEventListener("visibilitychange",function(){if(!document.hidden&&autoGet()&&!AUTO.timer&&!AUTO.due&&location.protocol!=="file:")refreshNow($("#rmsg"),$("#refresh"))});
function initRefresh(saveView){
  var b=$("#refresh"),msg=$("#rmsg");
  AUTO.save=saveView;
  if(window.__refreshBound)return;window.__refreshBound=1;  // الصفحة الواحدة تضمّ عدّة نسخ من هذا الملف: زرّ التحديث يُربط مرة واحدة
  b.addEventListener("click",function(){refreshNow(msg,b)});
  age();setInterval(age,30000);autoArm();
}

/* ---------- السمة (نهاري/ليلي/تلقائي): مشتركة بين كل الصفحات، تُحفظ في localStorage وتُطبَّق مبكرًا من ui_theme_head.js ---------- */
(function(){
  var KEY="mu_theme",ORDER=["auto","light","dark"],LBL={auto:"السمة: تلقائية",light:"السمة: نهارية",dark:"السمة: ليلية"},nav=document.getElementById("themeslot")||document.querySelector(".nav");
  if(!nav||nav.querySelector(".themebtn"))return;
  function get(){try{var t=localStorage.getItem(KEY);return t==="light"||t==="dark"?t:"auto"}catch(e){return "auto"}}
  function apply(t){
    if(t==="auto")document.documentElement.removeAttribute("data-theme");else document.documentElement.setAttribute("data-theme",t);
    b.textContent=LBL[t];b.setAttribute("aria-label",LBL[t]+"؛ اضغط للتبديل");
  }
  var b=document.createElement("button");b.type="button";b.className="themebtn";
  b.addEventListener("click",function(){var t=ORDER[(ORDER.indexOf(get())+1)%3];try{if(t==="auto")localStorage.removeItem(KEY);else localStorage.setItem(KEY,t)}catch(e){}apply(t)});
  nav.appendChild(b);apply(get());
})();

/* ---------- التحديث الدوري: زر تحت زر السمة يدور بين إيقاف و5 و15 و30 دقيقة (مؤقّته في autoArm بعد تهيئة الصفحة) ---------- */
(function(){
  var nav=document.getElementById("themeslot");
  if(!nav||nav.querySelector("#autobtn"))return;
  function lbl(m){return m?"التحديث الدوري: كل "+m+(m<=10?" دقائق":" دقيقة"):"التحديث الدوري: إيقاف"}
  var b=document.createElement("button");b.type="button";b.className="themebtn autobtn";b.id="autobtn";
  function apply(m){b.textContent=lbl(m);b.setAttribute("aria-label",lbl(m)+"؛ اضغط للتبديل")}
  b.addEventListener("click",function(){
    var m=AUTO.steps[(AUTO.steps.indexOf(autoGet())+1)%AUTO.steps.length];
    try{if(m)localStorage.setItem(AUTO.key,String(m));else localStorage.removeItem(AUTO.key)}catch(e){}
    apply(m);autoArm();
  });
  nav.appendChild(b);apply(autoGet());
})();

/* ---------- المرشِّحات: مطويّة افتراضيًّا في الشاشات الضيّقة، وملخّصها يعرض الفترة الحالية ---------- */
(function(){
  var box=document.getElementById("fbox"),sum=document.getElementById("fsum");
  if(!box)return;
  if(window.matchMedia&&matchMedia("(max-width:640px)").matches)box.removeAttribute("open");
  function upd(){
    var p=box.querySelector("#presets [aria-pressed=true]"),f=box.querySelector("#from"),t=box.querySelector("#to");
    sum.textContent=p?"· "+p.textContent.trim():(f&&f.value?"· "+f.value+" → "+t.value:"");
  }
  box.addEventListener("click",function(){setTimeout(upd,0)});box.addEventListener("change",function(){setTimeout(upd,0)});
  setTimeout(upd,300);
})();

/*@@PAGE_STATE@@*/ /* ما بعد هذا السطر يعتمد على حالة الجزء (S وD وFIRST وLAST وrender) ويُضمَّن داخل كل جزء؛ ما قبله مشترك يُضمَّن مرة واحدة في الصفحة */
/* ---------- مرشِّحات الفترة والنماذج (مشتركة: تفترض S وD وLAST وFIRST وrender في نطاق الصفحة) ---------- */
function setPreset(p){
  S.preset=p;S.to=LAST;
  S.from=p==="all"?FIRST:addDays(LAST,-(Number(p)-1));
  if(S.from<FIRST)S.from=FIRST;syncInputs();
}
function syncInputs(){
  $("#from").value=S.from;$("#to").value=S.to;
  [].forEach.call($("#presets").children,function(b){b.setAttribute("aria-pressed",String(b.dataset.p===S.preset))});
}
function buildChips(){
  var box=$("#chips");clear(box);
  D.models.forEach(function(m,i){
    var b=mk("button",{type:"button",class:"chip","aria-pressed":String(S.models.has(i))});
    var sw=mk("span",{class:"sw"});sw.style.background=css(MCOL[i]);b.appendChild(sw);b.appendChild(mk("span",null,m));
    b.addEventListener("click",function(){
      if(S.models.has(i))S.models.delete(i);else S.models.add(i);
      if(!S.models.size)D.models.forEach(function(_,j){S.models.add(j)});
      buildChips();render();
    });box.appendChild(b);
  });
}
function inRange(day){return day>=S.from&&day<=S.to}
/* دلتا الفترة: فترة سابقة مساوية الطول متّصلة قبل S.from؛ لا دلتا عند «الكل» أو إن لم تكتمل السابقة في القاعدة أو كان سابقها صفرًا */
/* الفترة السابقة المساوية بأيام كاملة: إن شملت الفترة الحالية اليوم الجاري (UTC) استُبعد من الطرفين (curTo آخر يوم كامل، cut=true) فلا يُقارن يوم ناقص بيوم كامل */
function prevRange(){
  if(S.preset==="all"||!S.from)return null;
  var today=ymd(Date.now()),cut=S.to>=today,curTo=cut?addDays(today,-1):S.to;
  if(curTo<S.from)return null;
  var n=Math.round((Date.parse(curTo+"T00:00:00Z")-Date.parse(S.from+"T00:00:00Z"))/864e5)+1,pf=addDays(S.from,-n);
  return pf>=FIRST?{from:pf,to:addDays(S.from,-1),n:n,curTo:curTo,cut:cut}:null}
function inPrev(day,p){return !!p&&day>=p.from&&day<=p.to}
function inCur(day,p){return !!p&&day>=S.from&&day<=p.curTo}  // طرف الفترة الحالية في الدلتا: الأيام الكاملة فقط
function deltaSfx(p){return " عن الفترة السابقة"+(p&&p.cut?" (أيام كاملة)":"")}
function deltaText(cur,prev,p){if(cur==null||prev==null||!(prev>0)||isNaN(cur))return "";var r=cur/prev-1;return (r>0?"▲ +":r<0?"▼ −":"= ")+pct(Math.abs(r),0)+deltaSfx(p)}
function deltaPts(cur,prev,p){if(cur==null||prev==null||isNaN(cur)||isNaN(prev))return "";var r=(cur-prev)*100;return (r>0?"▲ +":r<0?"▼ −":"= ")+num(Math.abs(r),1)+" نقطة"+deltaSfx(p)}  // لمؤشرات النسب: فرق بالنقاط المئوية لا تغيّر نسبي
/* فراغات التعريفات (من سجلّ المقاييس) تُملأ بأرقام الحمولة */
function fillDefs(m){Object.keys(m).forEach(function(k){[].forEach.call(document.querySelectorAll('[data-fill="'+k+'"]'),function(e){e.textContent=m[k]})})}
function bindFilters(){
  [].forEach.call($("#presets").children,function(b){b.addEventListener("click",function(){setPreset(b.dataset.p);render()})});
  function custom(){var f=$("#from").value,t=$("#to").value;if(!f||!t||f>t)return;S.from=f;S.to=t;S.preset="custom";syncInputs();render()}
  $("#from").addEventListener("change",custom);$("#to").addEventListener("change",custom);
  $("#from").min=FIRST;$("#from").max=LAST;$("#to").min=FIRST;$("#to").max=LAST;
}
