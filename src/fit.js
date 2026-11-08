/* لا تمريرَ أفقيًّا في الجداول: ما لا يتّسع منها يُكدَّس صفوفًا (.stack) بتسمية كلّ خليّة بعنوان عمودها. يُعاد الفحص عند تغيّر العرض أو المحتوى. */
(function(){
  var queued=0;
  function label(t){
    var heads=[].map.call(t.querySelectorAll("thead th"),function(h){return h.textContent.trim()});
    [].forEach.call(t.querySelectorAll("tbody tr, tfoot tr"),function(r){
      [].forEach.call(r.children,function(td,i){if(!td.hasAttribute("data-l")&&heads[i])td.setAttribute("data-l",heads[i])});
    });
  }
  function fit(){
    queued=0;
    [].forEach.call(document.querySelectorAll(".wrap > table"),function(t){
      if(!t.offsetParent&&!t.classList.contains("stack"))return;
      t.classList.remove("stack");
      var w=t.parentElement;
      var min=+t.getAttribute("data-min")||0; /* جدولٌ أضيق من حدّه الأدنى يُكدَّس قبل أن يضيق عنوانه */
      if(w.scrollWidth>w.clientWidth+1||(min&&w.clientWidth<min)){label(t);t.classList.add("stack")}
    });
  }
  function later(){if(!queued){queued=1;setTimeout(fit,30)}}
  window.addEventListener("resize",later);
  window.addEventListener("hashchange",function(){setTimeout(later,50)});
  new MutationObserver(later).observe(document.body,{childList:true,subtree:true});
  later();
})();
